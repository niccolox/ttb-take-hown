"""Troubled-application AI review: trigger math, the post-settle hook, and
the suggestion-only enrichment contract (AD-41: settled never reopens)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.jobs import JobQueue, ResultStore
from api.review import TRIGGER_RATIO, run_ai_review, troubled_stats


def _field(name, status, reason=None):
    return {"field": name, "status": status, "reason_code": reason}


TROUBLED_FIELDS = [
    _field("brand_name", "MISMATCH", "text_differs"),
    _field("class_type", "NEEDS_REVIEW", "low_confidence"),
    _field("alcohol_content", "MISMATCH", "value_out_of_tolerance"),
    _field("net_contents", "MATCH"),
    _field("government_warning", "NEEDS_REVIEW", "not_found"),
    _field("name_address", "NOT_CHECKED"),          # excluded from the ratio
]


class FakeClient:
    model = "fake-model"
    _dialect = "chat"

    def __init__(self, text="- Pattern: mixed.\n- Examine Brand name first."):
        self.text = text
        self.calls = []

    def available(self):
        return True

    def complete(self, system, user):
        self.calls.append((system, user))
        return self.text


class OffClient:
    def available(self): return False
    def complete(self, s, u): raise AssertionError("must not be called")


def _store_with(fields, rid="r1"):
    store = ResultStore()
    entry = store.put({"request_id": rid, "fields": fields})
    entry.meta["app_data"] = {"brand_name": "OLD TOM", "beverage_type": "wine"}
    return store


# -- trigger math -----------------------------------------------------------

def test_ratio_excludes_not_checked():
    s = troubled_stats(TROUBLED_FIELDS)
    assert s["counted"] == 5 and s["flagged"] == 4
    assert s["ratio"] == 0.8 and s["triggered"]


def test_below_threshold_not_triggered():
    fields = [_field("a", "MISMATCH")] + [_field(c, "MATCH") for c in "bcd"]
    s = troubled_stats(fields)
    assert s["ratio"] == 0.25 and not s["triggered"]


def test_exactly_half_triggers():
    fields = [_field("a", "MISMATCH"), _field("b", "NEEDS_REVIEW"),
              _field("c", "MATCH"), _field("d", "NOT_REQUIRED")]
    assert troubled_stats(fields)["triggered"]
    assert TRIGGER_RATIO == 0.5


def test_all_not_checked_never_triggers():
    assert not troubled_stats([_field("a", "NOT_CHECKED")])["triggered"]
    assert not troubled_stats([])["triggered"]


# -- run_ai_review ----------------------------------------------------------

def test_review_attaches_enrichment_with_debug():
    store = _store_with(TROUBLED_FIELDS)
    client = FakeClient()
    run_ai_review("r1", store, client)
    ai = store.get("r1").result["enrichments"]["ai_review"]
    assert ai["text"].startswith("- Pattern")
    dbg = ai["debug"]
    assert dbg["ratio"] == 0.8 and dbg["threshold"] == 0.5
    assert dbg["model"] == "fake-model" and dbg["fallback"] is False
    assert {f["field"] for f in dbg["flagged_fields"]} == {
        "brand_name", "class_type", "alcohol_content", "government_warning"}
    # prompt carried the statuses and fenced the applicant data
    system, user = client.calls[0]
    assert "MISMATCH" in user and "<untrusted>" in user
    assert "advisory" in system


def test_review_is_suggestion_only():
    store = _store_with(TROUBLED_FIELDS)
    before = [dict(f) for f in store.get("r1").result["fields"]]
    run_ai_review("r1", store, FakeClient())
    assert store.get("r1").result["fields"] == before   # no status touched


def test_below_threshold_no_enrichment():
    fields = [_field("a", "MISMATCH")] + [_field(c, "MATCH") for c in "bcd"]
    store = _store_with(fields)
    client = FakeClient()
    run_ai_review("r1", store, client)
    assert "enrichments" not in store.get("r1").result
    assert not client.calls


def test_unconfigured_client_is_silent():          # D3: absence stays absence
    store = _store_with(TROUBLED_FIELDS)
    run_ai_review("r1", store, OffClient())
    assert "enrichments" not in store.get("r1").result


def test_empty_model_text_falls_back_deterministically():
    store = _store_with(TROUBLED_FIELDS)
    run_ai_review("r1", store, FakeClient(text=None))
    ai = store.get("r1").result["enrichments"]["ai_review"]
    assert ai["debug"]["fallback"] is True
    assert "unavailable" in ai["disclaimer"]
    assert "Brand name" in ai["text"]              # flagged rows named
    assert ai["text"].count("\n") <= 9             # bullet cap holds


def test_second_run_does_not_reclaim():
    store = _store_with(TROUBLED_FIELDS)
    first = FakeClient()
    run_ai_review("r1", store, first)
    again = FakeClient(text="- different text")
    run_ai_review("r1", store, again)
    assert not again.calls                          # dedupe: one review per result
    ai = store.get("r1").result["enrichments"]["ai_review"]
    assert ai["text"].startswith("- Pattern")


def test_revision_bumps_for_pending_and_final():
    store = _store_with(TROUBLED_FIELDS)
    rev0 = store.get("r1").revision
    run_ai_review("r1", store, FakeClient())
    assert store.get("r1").revision == rev0 + 2     # pending + attach (AD-32)


# -- the post-settle hook ---------------------------------------------------

def test_jobqueue_fires_post_settle_on_last_terminal():
    store = _store_with(TROUBLED_FIELDS, rid="hooked")
    q = JobQueue(store, workers=2)
    fired = []
    q.post_settle = fired.append
    try:
        q.submit("hooked", "j1", lambda: None)
        deadline = time.monotonic() + 5
        while not fired and time.monotonic() < deadline:
            time.sleep(0.02)
        assert fired == ["hooked"]
        assert store.get("hooked").settled()
    finally:
        q.shutdown()


def test_hook_exception_never_breaks_the_job():
    store = _store_with(TROUBLED_FIELDS, rid="boom")
    q = JobQueue(store, workers=2)
    q.post_settle = lambda rid: (_ for _ in ()).throw(RuntimeError("hook"))
    try:
        q.submit("boom", "j1", lambda: None)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            j = store.get("boom").jobs["j1"]
            if j.state == "done":
                break
            time.sleep(0.02)
        assert store.get("boom").jobs["j1"].state == "done"
    finally:
        q.shutdown()
