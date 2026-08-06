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


# ── env mode: prod gates (DevSecOps config matrix) ───────────────────────

def test_prod_gates_pipelines_and_samples_but_not_verify(monkeypatch):
    """Prod: samples empty, pipeline runs 403 — but the screening path
    (incl. batch import's POST /api/verify) stays fully enabled."""
    from fastapi.testclient import TestClient
    from api import main
    monkeypatch.setattr(main, "LABELCHECK_ENV", "prod")
    client = TestClient(main.app)
    assert client.get("/api/samples").json() == []
    r = client.post("/api/pipelines/wine/run")
    assert r.status_code == 403 and r.json()["code"] == "disabled_in_prod"
    # verify stays open (400 no_image = reached the handler, not a gate)
    assert client.post("/api/verify").status_code in (400, 503)
    assert client.get("/healthz").json()["env"] == "prod"


def test_dev_mode_keeps_everything(monkeypatch):
    from fastapi.testclient import TestClient
    from api import main
    monkeypatch.setattr(main, "LABELCHECK_ENV", "dev")
    client = TestClient(main.app)
    assert client.get("/healthz").json()["env"] == "dev"
    assert client.get("/api/samples").json() != []
    # unknown name → 404 from the handler itself: proves the prod gate is
    # NOT in the way, without kicking off a real registry pull from a test
    assert client.post("/api/pipelines/nope/run").status_code == 404


# ── batch-uploaded eval sets (dev/test tool) ─────────────────────────────

def _upload(client, name="my-set", csv=None, files=None):
    csv = csv if csv is not None else (
        "filename,beverage_type,brand_name,class_type,alcohol_content,net_contents,back_filename\r\n"
        "a.jpg,wine,BRAND A,Red Wine,12.5%,750 mL,\r\n"
        "b.jpg,wine,BRAND B,Red Wine,13%,750 mL,b_back.jpg\r\n")
    files = files if files is not None else ["a.jpg", "b.jpg", "b_back.jpg"]
    parts = [("images", (f, b"\xff\xd8fake", "image/jpeg")) for f in files]
    return client.post("/api/evalsets/upload", data={"name": name},
                       files=[("csv", ("m.csv", csv.encode(), "text/csv"))] + parts)


def test_evalset_upload_happy_path(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from api import main
    monkeypatch.setattr(main, "LABELCHECK_ENV", "dev")
    monkeypatch.setattr(main, "_EVAL", tmp_path)
    client = TestClient(main.app)
    r = _upload(client)
    assert r.status_code == 200, r.text
    assert r.json() == {"name": "upload_my-set", "count": 2}
    corpora = client.get("/api/corpora").json()
    names = corpora if isinstance(corpora, list) else list(corpora)
    assert any("upload_my-set" in str(n) for n in [names])
    import json as _json
    man = _json.loads((tmp_path / "uploads" / "my-set" / "manifest.json").read_text())
    assert man[1]["files"][1] == {"file": "b_back.jpg", "panel": "back"}
    # replace-by-name: uploading again succeeds and stays at 2
    assert _upload(client).json()["count"] == 2


def test_evalset_upload_gates_and_validation(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from api import main
    monkeypatch.setattr(main, "_EVAL", tmp_path)
    client = TestClient(main.app)
    monkeypatch.setattr(main, "LABELCHECK_ENV", "prod")
    assert _upload(client).status_code == 403          # prod refuses
    monkeypatch.setattr(main, "LABELCHECK_ENV", "stage")
    assert _upload(client).status_code == 403          # stage too
    monkeypatch.setattr(main, "LABELCHECK_ENV", "dev")
    assert _upload(client, name="Bad Name!").status_code == 400
    assert _upload(client, csv="filename\r\nmissing.jpg\r\n").status_code == 400
    r = _upload(client, files=["a.jpg", "../evil.jpg"])
    assert r.status_code == 400                        # unsafe filename
