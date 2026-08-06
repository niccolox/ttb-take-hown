"""mm second read (mm-ocr-augment T3/T10/T11/T13): the deterministic
judge, eligibility widening under LABELCHECK_MM_READ, replace-not-add
call semantics, budget-gated fallback, and the late-mutation guard."""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

import api.layers as layers
from api import mm_judge
from api.jobs import Job, JobQueue, ResultStore
from api.rules.warning import STATUTORY_WARNING
from api.vlm import MMRead

APP = {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM",
       "class_type": "Kentucky Straight Bourbon Whiskey",
       "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}


# ── judge (pure) ─────────────────────────────────────────────────────────

def test_judge_abv_match_sides_with_application_on_mismatch():
    v, note = mm_judge.judge("alcohol_content", "MISMATCH",
                             "45% ALC./VOL. (90 PROOF)", APP, "46% Alc./Vol.")
    assert v == "sides_with_application"


def test_judge_abv_confirming_the_machine_read_agrees():
    v, _ = mm_judge.judge("alcohol_content", "MISMATCH",
                          "46% ALC./VOL.", APP, "46% Alc./Vol.")
    assert v == "agrees"                       # the mismatch stands


def test_judge_abv_within_tolerance_is_agreement():
    app = {**APP, "alcohol_content": "45.2%"}
    v, _ = mm_judge.judge("alcohol_content", "NEEDS_REVIEW", "45% ALC/VOL",
                          app, None)
    assert v == "agrees"                       # WITHIN_TOLERANCE ⇒ legal match


def test_judge_abv_absent_from_transcription_differs():
    v, note = mm_judge.judge("alcohol_content", "NEEDS_REVIEW",
                             "OLD TOM DISTILLERY EST 1884", APP, None)
    assert v == "differs" and "no ABV" in note


def test_judge_warning_is_punctuation_and_case_insensitive():
    mangled = STATUTORY_WARNING.replace(",", ".").title()
    v, note = mm_judge.judge("government_warning", "MISMATCH", mangled, APP,
                             "GOVT WARNING truncated read")
    assert v == "sides_with_application"       # content words all present
    assert "typography" in note                # narrowed verdict, stated


def test_judge_generic_containment_and_differs():
    assert mm_judge.judge("brand_name", "NEEDS_REVIEW",
                          "★ OLD  TOM ★ DISTILLERY", APP, None)[0] == "agrees"
    assert mm_judge.judge("brand_name", "NEEDS_REVIEW",
                          "SEACLIFF ESTATE", APP, None)[0] == "differs"


# ── run_j3 wiring ────────────────────────────────────────────────────────

def _tiny_jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), "white").save(buf, "JPEG")
    return buf.getvalue()


class FakeMMVLM:
    engine_label = "gpt-4.1-vision"

    def __init__(self, result=None):
        self.result = result or MMRead("ok", text="45% ALC./VOL. (90 PROOF)")
        self.transcribes = 0
        self.questions = []

    def available(self, mode="question"):
        return True

    def transcribe_crop(self, crop_jpeg, context=None):
        self.transcribes += 1
        self.last_context = context
        return self.result

    def read_crop(self, crop_jpeg, question):
        self.questions.append(question)
        return "fallback answer"


@pytest.fixture
def store():
    s = ResultStore()
    fields = [
        {"field": "alcohol_content", "status": "NEEDS_REVIEW",
         "reason_code": "unreadable", "label_value": None, "note": "",
         "evidence": {"bbox": [5, 5, 60, 30], "panel": 0}},
        {"field": "brand_name", "status": "MISMATCH",
         "reason_code": "text_differs", "label_value": "OLO TOM", "note": "",
         "evidence": {"bbox": [5, 32, 60, 55], "panel": 0}},
        {"field": "net_contents", "status": "MATCH",
         "label_value": "750 mL", "note": ""},
    ]
    entry = s.put({"request_id": "r-1", "fields": fields})
    entry.meta.update(panels_jpeg=[_tiny_jpeg()], panel_words=[[]],
                      app_data=dict(APP), scales=[1.0], skew_tfs=[None])
    entry.jobs["vlm-assist"] = Job(layer="vlm-assist",
                                   submitted_at=time.monotonic(),
                                   deadline_s=45.0)
    entry.jobs["vlm-assist"].state = "running"
    return s


def test_mm_on_widens_to_mismatch_and_replaces_question(store, monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    vlm = FakeMMVLM()
    layers.run_j3("r-1", store, vlm)
    fields = {f["field"]: f for f in store.get("r-1").result["fields"]}
    abv, brand = fields["alcohol_content"], fields["brand_name"]
    # NEEDS_REVIEW row: transcription judged, app value found → agrees
    assert abv["mm_reread"]["verdict"] == "agrees"
    assert abv["mm_reread"]["model"] == "gpt-4.1-vision"
    assert abv["status"] == "NEEDS_REVIEW"            # suggestion-only holds
    # MISMATCH row joined the target set (amendment 17); the ABV
    # transcription doesn't contain the brand → differs (debug-only)
    assert brand["mm_reread"]["verdict"] == "differs"
    assert brand["status"] == "MISMATCH"
    # replace-not-add: transcription succeeded ⇒ zero question calls
    assert vlm.transcribes == 2 and vlm.questions == []
    assert abv["refinements"][-1]["kind"] == "mm-reread"
    assert abv["refinements"][-1]["applied"] is False
    assert "mm_reread" not in fields["net_contents"]  # green rows untouched


def test_mm_off_keeps_shipped_selection(store, monkeypatch):
    monkeypatch.delenv("LABELCHECK_MM_READ", raising=False)
    vlm = FakeMMVLM()
    layers.run_j3("r-1", store, vlm)
    fields = {f["field"]: f for f in store.get("r-1").result["fields"]}
    assert vlm.transcribes == 0                       # new path never runs
    assert "mm_reread" not in fields["alcohol_content"]
    assert "mm_reread" not in fields["brand_name"]    # MISMATCH still excluded
    assert fields["alcohol_content"]["vlm"]["suggestion"] == "fallback answer"
    assert fields["alcohol_content"]["vlm"]["engine"] == "gpt-4.1-vision"


def test_unreadable_falls_back_to_question_once(store, monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    vlm = FakeMMVLM(result=MMRead("unreadable"))
    layers.run_j3("r-1", store, vlm)
    fields = {f["field"]: f for f in store.get("r-1").result["fields"]}
    abv = fields["alcohol_content"]
    assert abv["mm_reread"]["verdict"] == "unreadable"
    assert abv["vlm"]["suggestion"] == "fallback answer"
    # fallback fired for the NEEDS_REVIEW row only — never for the widened
    # MISMATCH row (mm-only by design)
    assert len(vlm.questions) == 1


def test_error_carries_cause_and_no_fallback_without_budget(store, monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    job = store.get("r-1").jobs["vlm-assist"]
    job.submitted_at = time.monotonic() - 40.0        # ~5 s of budget left
    vlm = FakeMMVLM(result=MMRead("error", cause="timeout"))
    layers.run_j3("r-1", store, vlm)
    abv = {f["field"]: f for f in store.get("r-1").result["fields"]}["alcohol_content"]
    assert abv["mm_reread"] == {"verdict": "error", "cause": "timeout",
                                "text": None, "model": "gpt-4.1-vision",
                                "elapsed_ms": abv["mm_reread"]["elapsed_ms"]}
    assert vlm.questions == []                        # amendment 18: budget gate


def test_late_timeout_never_mutates_settled_result(store, monkeypatch):
    monkeypatch.setenv("LABELCHECK_MM_READ", "1")
    store.get("r-1").jobs["vlm-assist"].state = "timed_out"
    before = store.get("r-1").revision
    layers.run_j3("r-1", store, FakeMMVLM())
    entry = store.get("r-1")
    assert entry.revision == before                   # amendment 19: no-op
    assert all("mm_reread" not in f for f in entry.result["fields"])
