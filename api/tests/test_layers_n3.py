"""N3/N4 tests: merge_refinement property tests over the full status
lattice (AD-20), J1 guard/shadow behavior, J2 AD-20 concurrence — all
engine-free via canned verify results."""

from __future__ import annotations

import json

import pytest

import api.layers as layers
from api.jobs import JobQueue, ResultStore
from api.merge import classify, merge_refinement

# ------------------------------------------------------------- merge --


def _field(status="MATCH", label="GOVERNMENT WARNING…", **kw):
    return {"field": "government_warning", "status": status,
            "label_value": label, "note": "", **kw}


def test_downgrade_applies_immediately():
    f = _field("MATCH")
    changed = merge_refinement(f, _field("MISMATCH"), "second-engine-check",
                               "paddle", upgrade_ok=False)
    assert changed and f["status"] == "MISMATCH"
    assert f["refinements"][0]["applied"] is True
    assert f["refinements"][0]["kind"] == "downgrade"


def test_upgrade_without_corroboration_is_annotation_only():
    f = _field("MISMATCH")
    changed = merge_refinement(f, _field("MATCH"), "warning-reread",
                               "nemotron", upgrade_ok=False)
    assert not changed and f["status"] == "MISMATCH"     # never silently greened
    assert f["refinements"][0]["applied"] is False


def test_upgrade_with_corroboration_applies():
    f = _field("MISMATCH")
    changed = merge_refinement(f, _field("MATCH", note="clean re-read"),
                               "warning-reread", "nemotron", upgrade_ok=True)
    assert changed and f["status"] == "MATCH"


def test_discovery_applies_immediately_even_to_mismatch():
    f = _field("NOT_REQUIRED", label=None)
    changed = merge_refinement(f, _field("MISMATCH", label="45%"),
                               "warning-reread", "nemotron", upgrade_ok=False)
    assert changed and f["status"] == "MISMATCH"
    assert f["refinements"][0]["kind"] == "discovery"


def test_full_lattice_classification():
    # (base, new, base_located, new_located) -> kind
    cases = [
        ("MATCH", "MATCH", True, True, "same"),
        ("MATCH", "NEEDS_REVIEW", True, True, "downgrade"),
        ("MATCH", "MISMATCH", True, True, "downgrade"),
        ("NEEDS_REVIEW", "MISMATCH", True, True, "downgrade"),
        ("MISMATCH", "NEEDS_REVIEW", True, True, "upgrade"),
        ("NEEDS_REVIEW", "MATCH", True, True, "upgrade"),
        ("NOT_CHECKED", "MATCH", False, True, "discovery"),
        ("NOT_REQUIRED", "MISMATCH", False, True, "discovery"),
        ("WITHIN_TOLERANCE", "MISMATCH", True, True, "downgrade"),
        ("LIKELY_MATCH", "MATCH", True, True, "upgrade"),
    ]
    for base, new, bl, nl, want in cases:
        assert classify(base, new, bl, nl) == want, (base, new, want)


def test_provenance_always_recorded():
    f = _field("MATCH")
    merge_refinement(f, _field("MATCH"), "second-engine-check", "paddle",
                     upgrade_ok=False)
    merge_refinement(f, _field("MISMATCH"), "warning-reread", "nemotron",
                     upgrade_ok=False)
    assert len(f["refinements"]) == 2
    assert all({"layer", "engine", "from", "to", "kind", "applied"}
               <= set(r) for r in f["refinements"])


# ------------------------------------------------------------- layers --


class FakeExtractor:
    def __init__(self, words=None):
        self._words = words or []

    def ready(self):
        return True

    def extract(self, path):
        return self._words


def _tiny_jpeg() -> bytes:
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), "white").save(buf, "JPEG")
    return buf.getvalue()


def _canned(fields):
    return {"schema_version": "1", "request_id": "x", "screening_result": "s",
            "attention_state": "none", "timing_ms": {"total": 1},
            "fields": fields}


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setattr(layers, "TELEMETRY_PATH", tmp_path / "e4.jsonl")
    store = ResultStore()
    q = JobQueue(store, workers=1, bound=8, watchdog_interval_s=0.05)
    yield store, q, tmp_path
    q.shutdown()


def _seed(store, primary_fields):
    result = {"schema_version": "1", "request_id": "r-1",
              "screening_result": "s", "attention_state": "none",
              "timing_ms": {"total": 1}, "fields": primary_fields}
    entry = store.put(result)
    entry.meta.update(panels_jpeg=[_tiny_jpeg()], panel_words=[[]],
                      app_data={}, warn_bbox=None, warn_panel=0,
                      scales=[1.0], skew_tfs=[None])
    return entry


def test_j1_guard_disagreement_downgrades_with_both_reads(stack, monkeypatch):
    store, q, tmp = stack
    _seed(store, [_field("MATCH", label="GOVERNMENT WARNING: correct text"),
                  {"field": "brand_name", "status": "MATCH",
                   "label_value": "OLD TOM", "note": ""}])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([_field("MISMATCH", label="GOVT WARNING broken"),
                                 {"field": "brand_name", "status": "NEEDS_REVIEW",
                                  "label_value": None, "note": ""}]))
    layers.run_j1("r-1", store, FakeExtractor(), "paddle", q)
    entry = store.get("r-1")
    warn = entry.result["fields"][0]
    assert warn["status"] == "NEEDS_REVIEW"              # guard downgrade
    assert warn["reason_code"] == "engine_disagreement"
    assert warn["guard"]["state"] == "disagreed"
    assert warn["guard"]["qa_label_value"] == "GOVT WARNING broken"
    brand = entry.result["fields"][1]
    assert brand["status"] == "MATCH"                    # non-guard: shadow only
    assert "guard" not in brand
    rows = [json.loads(l) for l in (tmp / "e4.jsonl").read_text().splitlines()]
    assert {r["field"] for r in rows} == {"government_warning", "brand_name"}
    assert all("agree" in r for r in rows)


def test_j1_guard_disagreement_softens_red_to_review(stack, monkeypatch):
    """AD-16: red + green split locks the field at NEEDS_REVIEW with both
    reads — the differing second read is the corroboration."""
    store, q, _ = stack
    _seed(store, [_field("MISMATCH", label="GOVT WARNING broken")])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([_field("MATCH", label="GOVERNMENT WARNING: correct")]))
    layers.run_j1("r-1", store, FakeExtractor(), "paddle", q)
    warn = store.get("r-1").result["fields"][0]
    assert warn["status"] == "NEEDS_REVIEW"
    assert warn["reason_code"] == "engine_disagreement"
    assert warn["guard"]["state"] == "disagreed"


def test_j1_shadow_recovery_upgrades_read_quality_reviews(stack, monkeypatch):
    """Non-guard field stuck at NEEDS_REVIEW/possible_ocr_misread + clean QA
    read → two-read upgrade. `ambiguous` stays human."""
    store, q, _ = stack
    _seed(store, [{"field": "class_type", "status": "NEEDS_REVIEW",
                   "reason_code": "possible_ocr_misread",
                   "label_value": "Chardonnav", "note": ""},
                  {"field": "brand_name", "status": "NEEDS_REVIEW",
                   "reason_code": "ambiguous", "label_value": "X", "note": ""}])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([{"field": "class_type", "status": "MATCH",
                                  "label_value": "Chardonnay", "note": ""},
                                 {"field": "brand_name", "status": "MATCH",
                                  "label_value": "X", "note": ""}]))
    layers.run_j1("r-1", store, FakeExtractor(), "paddle", q)
    fields = {f["field"]: f for f in store.get("r-1").result["fields"]}
    assert fields["class_type"]["status"] == "MATCH"          # recovered
    assert fields["class_type"]["label_value"] == "Chardonnay"
    assert fields["brand_name"]["status"] == "NEEDS_REVIEW"   # ambiguous stays


def test_j1_guard_agreement_marks_confirmed(stack, monkeypatch):
    store, q, _ = stack
    _seed(store, [_field("MATCH")])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([_field("MATCH")]))
    layers.run_j1("r-1", store, FakeExtractor(), "paddle", q)
    warn = store.get("r-1").result["fields"][0]
    assert warn["status"] == "MATCH"
    assert warn["guard"]["state"] == "agreed"            # statutory MATCH shipped WITH agreement


def test_j1_chains_j2_on_retryable_warning(stack, monkeypatch):
    store, q, _ = stack
    _seed(store, [_field("MISMATCH", reason_code="statutory_text_differs")])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([_field("MATCH")]))
    submitted = []
    monkeypatch.setattr(q, "submit", lambda rid, layer, fn, **kw:
                        submitted.append(layer) or "pending")
    layers.run_j1("r-1", store, FakeExtractor(), "paddle", q,
                  gpu_extractor=FakeExtractor(), gpu_available=lambda: True)
    assert submitted == ["warning-reread"]


def test_j2_upgrade_requires_j1_concurrence(stack, monkeypatch):
    store, q, _ = stack
    entry = _seed(store, [_field("MISMATCH", reason_code="statutory_text_differs")])
    monkeypatch.setattr(layers, "verify_multi", lambda p, a, conf_floor=None:
                        _canned([_field("MATCH", note="clean crop read")]))
    # no J1 concurrence recorded → clean re-read must NOT green the field
    layers.run_j2("r-1", store, FakeExtractor(), "nemotron")
    warn = store.get("r-1").result["fields"][0]
    assert warn["status"] == "MISMATCH"
    assert warn["refinements"][-1]["applied"] is False
    # with J1 paddle concurrence → upgrade applies (AD-20 privileged read)
    entry.meta["j1_fields"] = {"government_warning":
                               {"status": "MATCH", "label_value": "…"}}
    layers.run_j2("r-1", store, FakeExtractor(), "nemotron")
    warn = store.get("r-1").result["fields"][0]
    assert warn["status"] == "MATCH"
    assert warn["refinements"][-1]["applied"] is True
