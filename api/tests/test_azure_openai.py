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
            assert "FIXED FACTS" in system
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
    # PASS-only endpoint
    assert client.post("/api/verify/sum-1/summary",
                       json={"decision": "FAIL"}).status_code == 400
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
