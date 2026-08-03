"""VLM provider dialects (plan E1, docs/plans/azure-enrichment-layers.md):
azure sends the structured content array + both auth headers; nvidia keeps
the NIM <img> dialect; off disables even with keys; the breaker trips
after 3 consecutive failures and recovers after cooloff."""

import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api import vlm
from api.vlm import NanoVLClient

CROP = b"\xff\xd8fakejpeg"


def _capture(monkeypatch, response=None, fail=False):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["payload"] = json.loads(req.data)
        if fail:
            raise urllib.error.URLError("down")
        body = json.dumps(response or {
            "choices": [{"message": {"content": "SEACLIFF ESTATE"}}]}).encode()
        return io.BytesIO(body)

    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_azure_dialect_content_array_and_headers(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_VLM_ENDPOINT", "https://r.openai.azure.com/openai/v1/chat/completions")
    monkeypatch.setenv("AZURE_VLM_KEY", "k123")
    monkeypatch.setenv("AZURE_VLM_MODEL", "gpt-vision-dep")
    cap = _capture(monkeypatch)
    c = NanoVLClient()
    assert c.available()
    assert c.read_crop(CROP, "What does the brand line say?") == "SEACLIFF ESTATE"
    msg = cap["payload"]["messages"][0]
    assert isinstance(msg["content"], list)                       # structured array
    kinds = [part["type"] for part in msg["content"]]
    assert kinds == ["text", "image_url"]
    assert msg["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert cap["headers"]["authorization"] == "Bearer k123"
    assert cap["headers"]["api-key"] == "k123"                    # classic endpoints
    assert cap["payload"]["model"] == "gpt-vision-dep"


def test_nvidia_dialect_unchanged(monkeypatch):
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nv1")
    cap = _capture(monkeypatch)
    c = NanoVLClient()
    assert c.read_crop(CROP, "Q?") == "SEACLIFF ESTATE"
    content = cap["payload"]["messages"][0]["content"]
    assert isinstance(content, str) and '<img src="data:image/jpeg' in content
    assert "api-key" not in cap["headers"]


def test_provider_off_disables_even_with_keys(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "off")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv1")
    monkeypatch.setenv("AZURE_VLM_KEY", "k123")
    assert NanoVLClient().available() is False


def test_azure_without_endpoint_is_silent(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_VLM_KEY", "k123")
    monkeypatch.delenv("AZURE_VLM_ENDPOINT", raising=False)
    c = NanoVLClient()
    assert c.available() is False and c.read_crop(CROP, "Q?") is None


def test_breaker_trips_and_recovers(monkeypatch):
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nv1")
    _capture(monkeypatch, fail=True)
    c = NanoVLClient()
    for _ in range(3):
        assert c.read_crop(CROP, "Q?") is None
    assert c.available() is False                     # cooling off
    # cooloff elapsed → available again, and a success resets the count
    c._cool_until = 0.0
    assert c.available() is True
    _capture(monkeypatch)                              # healthy transport again
    assert c.read_crop(CROP, "Q?") == "SEACLIFF ESTATE"
    assert c._fails == 0
