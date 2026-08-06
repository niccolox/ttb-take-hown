"""AzureVisionClient (successor to the deprecated NanoVLClient): gpt-4.1
chat-vision dialect, mistral_doc OCR branch, fixture demo, per-mode
breaker isolation, and the typed failure taxonomy."""

import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api import azure_openai
from api.azure_openai import (MMRead, AzureVisionClient,
                              VISION_BREAKER_FAILS)

CROP = b"\xff\xd8fakejpeg"


def _gpt41(monkeypatch):
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("AZ_GPT_4_1_URI",
                       "https://r.cognitiveservices.azure.com/openai/deployments/gpt-4.1/chat/completions?api-version=v")
    monkeypatch.setenv("AZ_GPT_4_1_KEY", "k41")
    monkeypatch.setenv("AZ_OPENAI_MODEL", "gpt-4.1")
    return AzureVisionClient()


def _capture(monkeypatch, response=None, fail=False, finish_reason=None,
             content="45% ALC./VOL. (90 PROOF)"):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data)
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        if fail:
            raise urllib.error.URLError("down")
        choice = {"message": {"content": content}}
        if finish_reason is not None:
            choice["finish_reason"] = finish_reason
        return io.BytesIO(json.dumps(
            response or {"choices": [choice]}).encode())

    monkeypatch.setattr(azure_openai.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_default_provider_is_gpt41(monkeypatch):
    c = _gpt41(monkeypatch)
    assert c.provider == "gpt41" and c.engine_label == "gpt-4.1"
    assert c.available() and c.available("transcribe")


def test_gpt41_transcribe_dialect(monkeypatch):
    cap = _capture(monkeypatch)
    r = _gpt41(monkeypatch).transcribe_crop(CROP)
    assert r == MMRead("ok", text="45% ALC./VOL. (90 PROOF)")
    msg = cap["payload"]["messages"][0]
    assert [p["type"] for p in msg["content"]] == ["text", "image_url"]
    assert "verbatim" in msg["content"][0]["text"]
    assert cap["payload"]["max_tokens"] == 600 and cap["timeout"] == 12
    assert cap["headers"]["authorization"] == "Bearer k41"
    assert cap["headers"]["api-key"] == "k41"      # classic deployment URLs


def test_gpt41_question_mode(monkeypatch):
    cap = _capture(monkeypatch, content="750 mL")
    assert _gpt41(monkeypatch).read_crop(CROP, "What net contents?") == "750 mL"
    assert cap["payload"]["max_tokens"] == 160 and cap["timeout"] == 30


def test_taxonomy_and_refusals(monkeypatch):
    c = _gpt41(monkeypatch)
    _capture(monkeypatch, finish_reason="length")
    assert c.transcribe_crop(CROP) == MMRead("error", cause="truncated")
    _capture(monkeypatch, content="I cannot read this image.")
    assert c.transcribe_crop(CROP).status == "unreadable"
    _capture(monkeypatch, response={"nope": 1})
    assert c.transcribe_crop(CROP).cause == "schema"
    assert c.transcribe_crop(b"x" * 200_001).cause == "oversized"
    monkeypatch.setenv("AZ_GPT_4_1_KEY", "")
    monkeypatch.setenv("AZ_OPENAI_API_KEY", "")
    assert AzureVisionClient().transcribe_crop(CROP).cause == "unconfigured"


def test_per_mode_breaker_isolation(monkeypatch):
    c = _gpt41(monkeypatch)
    _capture(monkeypatch, fail=True)
    for _ in range(VISION_BREAKER_FAILS):
        assert c.transcribe_crop(CROP).status == "error"
    assert c.available("transcribe") is False
    assert c.available() is True                    # question untouched
    assert c.transcribe_crop(CROP).cause == "breaker_open"
    _capture(monkeypatch)
    assert c.read_crop(CROP, "Q?") is not None


def test_vision_breaker_never_touches_text_client(monkeypatch):
    """The hard separation: a vision outage must not cool summaries."""
    monkeypatch.setenv("AZ_OPENAI_URI", "https://r/chat")
    monkeypatch.setenv("AZ_OPENAI_API_KEY", "k9")
    vision = _gpt41(monkeypatch)
    _capture(monkeypatch, fail=True)
    for _ in range(VISION_BREAKER_FAILS):
        vision.transcribe_crop(CROP)
    text = azure_openai.AzureOpenAIClient()
    assert text.available() is True                 # summaries unaffected


def test_mistral_doc_branch(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "mistral_doc")
    monkeypatch.setenv("MISTRAL_OCR_ENDPOINT", "https://r/ocr")
    monkeypatch.setenv("MISTRAL_OCR_KEY", "mk1")
    cap = _capture(monkeypatch,
                   response={"pages": [{"markdown": "GOVERNMENT WARNING: x"}]})
    c = AzureVisionClient()
    assert c.available("transcribe") and not c.available()
    assert c.read_crop(CROP, "Q?") is None          # OCR API: no chat
    r = c.transcribe_crop(CROP)
    assert r.status == "ok" and "GOVERNMENT WARNING" in r.text
    assert cap["payload"]["document"]["type"] == "image_url"
    assert "messages" not in cap["payload"]


def test_unknown_provider_falls_to_gpt41(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "gpt-4.1")
    monkeypatch.setenv("AZ_GPT_4_1_URI", "https://r/chat")
    monkeypatch.setenv("AZ_GPT_4_1_KEY", "k")
    assert AzureVisionClient().provider == "gpt41"
