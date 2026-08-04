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
