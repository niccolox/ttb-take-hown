"""Flag semantics + fixture provider (mm-ocr-augment T4/T20):
LABELCHECK_MM_READ default-off, the two no-egress cases tested
separately (amendment 27), chain-site availability union, and the
keyless fixture provider driving canned transcriptions into mm_reread."""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

import api.layers as layers
from api import vlm
from api.jobs import Job, ResultStore
from api.azure_openai import AzureVisionClient
from api.vlm import NanoVLClient

from .test_mm_reread import APP, _tiny_jpeg


def _mm_store():
    s = ResultStore()
    fields = [
        {"field": "alcohol_content", "status": "NEEDS_REVIEW",
         "reason_code": "unreadable", "label_value": None, "note": "",
         "evidence": {"bbox": [5, 5, 60, 30], "panel": 0}},
        {"field": "brand_name", "status": "MISMATCH",
         "reason_code": "text_differs", "label_value": "OLO TOM", "note": "",
         "evidence": {"bbox": [5, 32, 60, 55], "panel": 0}},
    ]
    entry = s.put({"request_id": "r-1", "fields": fields})
    entry.meta.update(panels_jpeg=[_tiny_jpeg()], panel_words=[[]],
                      app_data=dict(APP), scales=[1.0], skew_tfs=[None])
    entry.jobs["vlm-assist"] = Job(layer="vlm-assist",
                                   submitted_at=time.monotonic(),
                                   deadline_s=45.0, state="running")
    return s


def _spy_urlopen(monkeypatch, payloads):
    def fake_urlopen(req, timeout=0):
        payloads.append(json.loads(req.data))
        return io.BytesIO(json.dumps(
            {"choices": [{"message": {"content": "READ TEXT"}}]}).encode())
    monkeypatch.setattr(vlm.urllib.request, "urlopen", fake_urlopen)


# ── the two no-egress cases, separately (amendment 27) ───────────────────

def test_mm_off_means_zero_transcription_egress(monkeypatch):
    """Keys present, provider live, MM_READ unset: the shipped question
    calls still happen (that's today's J3), but NO transcription payload
    ever leaves — every request is the 160-token question shape."""
    monkeypatch.delenv("LABELCHECK_MM_READ", raising=False)
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nv1")
    payloads = []
    _spy_urlopen(monkeypatch, payloads)
    layers.run_j3("r-1", _mm_store(), NanoVLClient())
    assert payloads, "question mode should have fired (shipped behavior)"
    assert all(p["max_tokens"] == 160 for p in payloads)
    assert all("verbatim" not in p["messages"][0]["content"]
               for p in payloads if isinstance(p["messages"][0]["content"], str))


def test_key_absent_means_zero_egress_even_with_mm_on(monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    payloads = []
    _spy_urlopen(monkeypatch, payloads)
    store = _mm_store()
    before = store.get("r-1").revision
    layers.run_j3("r-1", store, NanoVLClient())
    assert payloads == []                          # zero egress entirely
    assert store.get("r-1").revision == before     # byte-identical no-op


# ── chain-site availability union (amendment 20 tail) ────────────────────

def test_union_submits_when_only_transcribe_mode_is_alive(monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    monkeypatch.delenv("LABELCHECK_VLM_PROVIDER", raising=False)
    monkeypatch.setenv("AZ_GPT_4_1_URI", "https://r/chat")
    monkeypatch.setenv("AZ_GPT_4_1_KEY", "k")
    c = AzureVisionClient()
    c._breaker["question"]["cool_until"] = time.monotonic() + 60
    assert c.available() is False
    assert layers._vlm_usable(c) is True           # transcribe keeps the job


def test_union_respects_flag_off(monkeypatch):
    monkeypatch.delenv("LABELCHECK_MM_READ", raising=False)
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "fixture")
    c = AzureVisionClient()
    assert layers._vlm_usable(c) is False          # fixture is transcribe-only
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    assert layers._vlm_usable(c) is True


# ── fixture provider (keyless demo, amendment 33) ────────────────────────

def test_fixture_provider_modes_and_echo(monkeypatch):
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "fixture")
    c = AzureVisionClient()
    assert c.available("transcribe") is True and c.available() is False
    assert c.read_crop(b"crop", "Q?") is None      # question mode disabled
    r = c.transcribe_crop(b"crop", context={"expected": "45% Alc./Vol."})
    assert r.status == "ok" and r.text == "45% Alc./Vol."
    assert c.transcribe_crop(b"crop").status == "unreadable"
    assert c.engine_label == "fixture"             # chips show it's a demo


def test_fixture_end_to_end_into_mm_reread(monkeypatch):
    """The keyless demo path at the layer level: no key, no network — the
    fixture echoes each field's expected value and the judge produces the
    demo verdicts (agrees on the unreadable row, sides_with_application on
    the mismatch row)."""
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    monkeypatch.setenv("LABELCHECK_VLM_PROVIDER", "fixture")
    monkeypatch.setattr(vlm.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("no network under fixture")))
    store = _mm_store()
    layers.run_j3("r-1", store, AzureVisionClient())
    fields = {f["field"]: f for f in store.get("r-1").result["fields"]}
    assert fields["alcohol_content"]["mm_reread"]["verdict"] == "agrees"
    assert fields["brand_name"]["mm_reread"]["verdict"] == "sides_with_application"
    assert fields["brand_name"]["mm_reread"]["model"] == "fixture"
    assert fields["alcohol_content"]["status"] == "NEEDS_REVIEW"  # suggestion-only
