"""Azure OpenAI client (third integration client, plan E3 building block):
payload/headers, silent no-op without config, breaker trip/recovery,
output-token cap. Same invariants as the VLM provider tests."""

import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api import azure_openai
from api.azure_openai import AzureOpenAIClient


def _capture(monkeypatch, fail=False, content="Two fields matched; one needs review."):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["payload"] = json.loads(req.data)
        if fail:
            raise urllib.error.URLError("down")
        return io.BytesIO(json.dumps(
            {"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", fake_urlopen)
    return captured


def _env(monkeypatch):
    # api.main imports load the real .env into os.environ — the NEW primary
    # names must be cleared or they outrank the monkeypatched fallbacks
    monkeypatch.delenv("AZ_GPT_4_1_URI", raising=False)
    monkeypatch.delenv("AZ_GPT_4_1_KEY", raising=False)
    monkeypatch.setenv("AZ_OPENAI_URI",
                       "https://r.services.ai.azure.com/models/chat/completions?api-version=x")
    monkeypatch.setenv("AZ_OPENAI_API_KEY", "k9")
    monkeypatch.setenv("AZ_OPENAI_MODEL", "gpt-test")


def test_payload_and_dual_auth_headers(monkeypatch):
    _env(monkeypatch)
    cap = _capture(monkeypatch)
    c = AzureOpenAIClient()
    out = c.complete("You summarize screening results.", "Summarize: ...")
    assert out == "Two fields matched; one needs review."
    assert cap["headers"]["authorization"] == "Bearer k9"
    assert cap["headers"]["api-key"] == "k9"
    p = cap["payload"]
    assert p["model"] == "gpt-test" and p["temperature"] == 0.0
    assert [m["role"] for m in p["messages"]] == ["system", "user"]


def test_output_token_cap(monkeypatch):
    _env(monkeypatch)
    cap = _capture(monkeypatch)
    AzureOpenAIClient().complete("s", "u", max_tokens=999_999)
    assert cap["payload"]["max_tokens"] == azure_openai.MAX_OUTPUT_TOKENS


def test_silent_without_config(monkeypatch):
    monkeypatch.delenv("AZ_OPENAI_URI", raising=False)
    monkeypatch.delenv("AZ_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZ_GPT_4_1_URI", raising=False)
    monkeypatch.delenv("AZ_GPT_4_1_KEY", raising=False)
    c = AzureOpenAIClient()
    assert c.available() is False and c.complete("s", "u") is None


def test_breaker_trips_and_recovers(monkeypatch):
    _env(monkeypatch)
    _capture(monkeypatch, fail=True)
    c = AzureOpenAIClient()
    for _ in range(3):
        assert c.complete("s", "u") is None
    assert c.available() is False
    c._cool_until = 0.0
    _capture(monkeypatch)
    assert c.complete("s", "u") is not None and c._fails == 0


# ── PASS-summary endpoint (E3/E4, PASS-scoped) ───────────────────────────────

def _fake_store_result(fields):
    from api import main
    from api.jobs import ResultStore
    store = ResultStore()
    entry = store.put({"schema_version": "1", "request_id": "sum-1",
                       "screening_result": "no_mismatch_found",
                       "attention_state": "none", "timing_ms": {"total": 1},
                       "fields": fields})
    return store, entry


def test_pass_summary_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main

    class FakeClient:
        model = "gpt-test"
        def available(self): return True
        def complete(self, system, user):
            assert "FIXED FACT" in system
            assert "<untrusted>" in user and "PASS" in user
            return "All checks matched; the warning was verified against the statutory text."

    fields = [{"field": "brand_name", "status": "MATCH", "note": ""}]
    store, _ = _fake_store_result(fields)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", FakeClient())
    client = TestClient(main.app)
    r = client.post("/api/verify/sum-1/summary",
                    json={"decision": "PASS", "at": "t", "application": {"brand_name": "X"}})
    assert r.status_code == 200
    assert "matched" in r.json()["text"] and r.json()["model"] == "gpt-test"
    # PASS and FAIL are the recordable decisions; open states are not
    assert client.post("/api/verify/sum-1/summary",
                       json={"decision": "NEEDS REVIEW"}).status_code == 400
    # unknown result
    assert client.post("/api/verify/nope/summary",
                       json={"decision": "PASS"}).status_code == 404


def test_pass_summary_silent_paths(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main

    class Unavailable:
        model = "m"
        def available(self): return False
        def complete(self, *a): raise AssertionError("must not be called")

    monkeypatch.setattr(main, "azoai_client", Unavailable())
    client = TestClient(main.app)
    r = client.post("/api/verify/x/summary", json={"decision": "PASS"})
    assert r.status_code == 204 and r.content == b""   # D3: absence, not error

    class Liar:
        model = "m"
        def available(self): return True
        def complete(self, system, user):
            return "The brand name failed to match the application."

    fields = [{"field": "brand_name", "status": "MATCH", "note": ""}]
    store, _ = _fake_store_result(fields)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", Liar())
    r2 = client.post("/api/verify/sum-1/summary", json={"decision": "PASS"})
    assert r2.status_code == 204                        # contradiction dropped


def test_contradiction_check_unit():
    from api.summary import contradicts
    green = [{"field": "a", "status": "MATCH"}]
    red = [{"field": "a", "status": "MISMATCH"}]
    assert contradicts(green, "the field failed to match") is True
    assert contradicts(green, "everything matched cleanly") is False
    assert contradicts(red, "one field is a mismatch, decided PASS anyway") is False


def test_responses_dialect_fallback(monkeypatch):
    """Foundry gateways can route a deployment to the Responses API — the
    client must flip dialect on the 'moved to input' hint and parse
    output_text, then stick with responses for subsequent calls."""
    import email.message
    _env(monkeypatch)
    calls = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data)
        calls.append(payload)
        if "messages" in payload:
            hdrs = email.message.Message()
            raise urllib.error.HTTPError(
                req.full_url, 400, "bad", hdrs,
                io.BytesIO(b'{"error":{"message":"Unsupported parameter: \'messages\'. '
                           b'In the Responses API, this parameter has moved to \'input\'."}}'))
        assert "input" in payload and "max_output_tokens" in payload
        return io.BytesIO(json.dumps({"output_text": "All clear summary."}).encode())

    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", fake_urlopen)
    c = AzureOpenAIClient()
    assert c.complete("s", "u") == "All clear summary."
    assert c._dialect == "responses" and len(calls) == 2
    assert c.complete("s", "u") == "All clear summary."
    assert len(calls) == 3                       # no chat retry the second time


def test_responses_text_extraction_output_array():
    body = {"output": [{"type": "reasoning"},
                       {"type": "message", "content": [
                           {"type": "output_text", "text": "Part one."},
                           {"type": "output_text", "text": "Part two."}]}]}
    assert AzureOpenAIClient._responses_text(body) == "Part one. Part two."


def test_debug_mode_logs_without_leaking_the_key(monkeypatch, caplog):
    """OPENAI_DEBUG=true emits request/response/error detail — and the API
    key must never appear in any log line, in any mode."""
    import logging
    _env(monkeypatch)
    monkeypatch.setenv("OPENAI_DEBUG", "true")
    _capture(monkeypatch)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        c = AzureOpenAIClient()
        assert c.complete("system rules", "summarize the result") is not None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "[openai-debug]" in text
    assert "→ chat" in text and "model=gpt-test" in text
    assert "text (" in text                          # response text logged
    assert "k9" not in text                          # the key, never
    # failures log the error body in debug mode
    caplog.clear()
    _capture(monkeypatch, fail=True)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        c.complete("s", "u")
    assert "✗" in "\n".join(r.getMessage() for r in caplog.records)


def test_debug_off_is_quiet(monkeypatch, caplog):
    import logging
    _env(monkeypatch)
    monkeypatch.delenv("OPENAI_DEBUG", raising=False)
    _capture(monkeypatch)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        AzureOpenAIClient().complete("s", "u")
    assert "[openai-debug]" not in "\n".join(r.getMessage() for r in caplog.records)


def test_responses_endpoint_autodetected(monkeypatch):
    monkeypatch.delenv("AZ_GPT_4_1_URI", raising=False)
    monkeypatch.delenv("AZ_GPT_4_1_KEY", raising=False)
    monkeypatch.setenv("AZ_OPENAI_URI",
                       "https://r.cognitiveservices.azure.com/openai/responses?api-version=x")
    monkeypatch.setenv("AZ_OPENAI_API_KEY", "k9")
    monkeypatch.setenv("AZ_OPENAI_MODEL", "m")
    cap = _capture(monkeypatch)

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data)
        assert "input" in payload and "messages" not in payload   # no chat round trip
        return io.BytesIO(json.dumps({"output_text": "hi"}).encode())
    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", fake_urlopen)
    c = AzureOpenAIClient()
    assert c._dialect == "responses"
    assert c.complete("s", "u") == "hi"


def test_prompt_v2_quality_and_overrides():
    from api.summary import build_user_prompt, quality_facts
    fields = [
        {"field": "brand_name", "status": "MATCH", "note": "",
         "evidence": {"panel": 0}},
        {"field": "government_warning", "status": "MISMATCH",
         "note": "title case", "reason_code": None, "evidence": {"panel": 1}},
        {"field": "net_contents", "status": "NEEDS_REVIEW",
         "reason_code": "not_visible_in_image", "note": "check the bottle"},
    ]
    result = {"fields": fields, "timing_ms": {"total": 5100}}
    overrides = {"whole": {"value": "PASS", "original": "Needs correction"},
                 "fields": {"government_warning": {"value": "PASS", "at": "t"},
                            "net_contents": {"value": "PASS", "at": "t"}}}
    p = build_user_prompt(fields, {"brand_name": "X"}, "t",
                          overrides=overrides, result=result)
    assert "Panels submitted: 2" in p
    assert "Machine-verified clean: 1 of 3 checks" in p
    assert "statement not visible (may be molded into the container)" in p
    assert p.count("AGENT OVERRIDE: decided PASS") == 2
    assert "Machine state at decision time: Needs correction." in p
    assert "First screening answer in 5.1 s" in p
    # clean submission phrasing
    clean = quality_facts({"fields": [{"field": "a", "status": "MATCH"}]})
    assert any("none — all statements located and readable" in f for f in clean)


def test_summary_endpoint_rejects_oversized_overrides(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main

    class FakeClient:
        model = "m"
        def available(self): return True
        def complete(self, s, u): return "ok summary"

    store, _ = _fake_store_result([{"field": "brand_name", "status": "MATCH"}])
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", FakeClient())
    client = TestClient(main.app)
    bad = {"decision": "PASS",
           "overrides": {"fields": {f"f{i}": {"value": "PASS"} for i in range(25)}}}
    assert client.post("/api/verify/sum-1/summary", json=bad).status_code == 400
    ok = {"decision": "PASS",
          "overrides": {"whole": {"value": "PASS", "original": "All clear"},
                        "fields": {"brand_name": {"value": "PASS", "at": "t"}}}}
    assert client.post("/api/verify/sum-1/summary", json=ok).status_code == 200


def test_responses_incomplete_retries_with_doubled_cap(monkeypatch):
    monkeypatch.delenv("AZ_GPT_4_1_URI", raising=False)
    monkeypatch.delenv("AZ_GPT_4_1_KEY", raising=False)
    monkeypatch.setenv("AZ_OPENAI_URI", "https://r.x/openai/responses?api-version=v")
    monkeypatch.setenv("AZ_OPENAI_API_KEY", "k9")
    monkeypatch.setenv("AZ_OPENAI_MODEL", "m")
    caps = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data)
        caps.append(payload["max_output_tokens"])
        if len(caps) == 1:
            return io.BytesIO(json.dumps(
                {"status": "incomplete", "output_text": "truncated…"}).encode())
        return io.BytesIO(json.dumps(
            {"status": "completed", "output_text": "Full two-paragraph record."}).encode())
    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", fake_urlopen)
    c = AzureOpenAIClient()
    assert c.complete("s", "u") == "Full two-paragraph record."
    assert caps == [azure_openai.MAX_OUTPUT_TOKENS,
                    min(azure_openai.MAX_OUTPUT_TOKENS * 2, 6000)]


def test_decisions_trailer_deterministic():
    from api.summary import decisions_trailer
    fields = [{"field": "government_warning", "status": "MISMATCH"}]
    ov = {"whole": {"value": "PASS", "original": "Needs correction"},
          "fields": {"government_warning": {"value": "PASS", "at": "t"}}}
    tr = decisions_trailer(fields, ov, "2026-08-03 20:20")
    assert "Government Warning — machine found MISMATCH, agent decided PASS" in tr
    assert "machine state at decision time: Needs correction" in tr
    # clean pass, no overrides → just the whole-label line
    tr2 = decisions_trailer([{"field": "a", "status": "MATCH"}], {}, "t")
    assert tr2 == "Agent decisions on record: Whole label: PASS recorded t."


def test_fail_summary_bullets_and_trailer(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main

    class FakeClient:
        model = "m"
        def available(self): return True
        def complete(self, system, user):
            assert "bullet lines only" in system.lower() or "bullet" in system
            assert "Whole-label decision: FAIL" in user
            return ("- Government Warning: MISMATCH — printed in title case\n"
                    "- Alcohol content: MATCH\n"
                    "- One panel submitted; all statements readable")

    fields = [{"field": "government_warning", "status": "MISMATCH", "note": "title case"}]
    store, _ = _fake_store_result(fields)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", FakeClient())
    client = TestClient(main.app)
    r = client.post("/api/verify/sum-1/summary",
                    json={"decision": "FAIL", "at": "t",
                          "overrides": {"whole": {"value": "FAIL", "original": "Needs correction"}}})
    assert r.status_code == 200
    text = r.json()["text"]
    assert text.startswith("- Government Warning")
    assert "Whole label: FAIL recorded t" in text
    assert "machine state at decision time: Needs correction" in text
    # failure language on a failing label never trips the PASS-only check
    assert "MISMATCH" in text


def test_no_text_falls_back_to_deterministic_record(monkeypatch):
    """A configured client whose model returns nothing must never cost the
    agent the record — deterministic bullets from the recorded facts, with
    the disclaimer saying so. D3 unchanged: unconfigured stays 204."""
    from fastapi.testclient import TestClient
    from api import main

    class EmptyModel:
        model = "Kimi-K2.6"
        def available(self): return True
        def complete(self, s, u): return None       # thinking ate the budget

    fields = [{"field": "government_warning", "status": "MISMATCH",
               "note": "title case"},
              {"field": "brand_name", "status": "MATCH", "note": ""}]
    store, _ = _fake_store_result(fields)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", EmptyModel())
    client = TestClient(main.app)
    r = client.post("/api/verify/sum-1/summary",
                    json={"decision": "FAIL", "at": "t",
                          "overrides": {"whole": {"value": "FAIL", "original": "Needs correction"},
                                        "fields": {"government_warning": {"value": "FAIL", "at": "t"}}}})
    assert r.status_code == 200
    body = r.json()
    assert body["text"].startswith("- ")
    assert "Government Warning: MISMATCH" in body["text"]
    assert "Clean checks: Brand name." in body["text"]
    assert "Override — Government Warning: machine found MISMATCH" in body["text"]
    assert "Whole label: FAIL recorded t" in body["text"]       # trailer still appended
    assert "AI draft unavailable" in body["disclaimer"]
    assert "recorded facts" in body["model"]
