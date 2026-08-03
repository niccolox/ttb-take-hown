"""N1 foundation tests (PLAN-enrichment): job queue, result store,
server-side terminality, finality contract, healthz schema, event-loop
liveness. Engine-free — extractor is faked where the app is involved."""

from __future__ import annotations

import threading
import time

import pytest

from api.jobs import (CANCELLED, DONE, FAILED, LOST, PENDING, SHED, TIMED_OUT,
                      JobQueue, ResultStore)


def _result(rid="r-1"):
    return {"schema_version": "1", "request_id": rid, "screening_result":
            "no_mismatch_found", "attention_state": "none",
            "timing_ms": {"total": 1}, "fields": []}


def _wait(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------- store --

def test_put_get_and_finality_contract():
    store = ResultStore()
    entry = store.put(_result())
    body = entry.public()
    assert body["result_id"] == "r-1"          # AD-36: result_id == request_id
    assert body["status"] == "settled" and body["settled"] is True
    assert body["pending"] == [] and body["revision"] == 1


def test_revision_bumps_on_every_mutation():
    store = ResultStore()
    store.put(_result())
    for expected in (2, 3, 4):
        assert store.mutate("r-1", lambda e: None)
        assert store.get("r-1").revision == expected


def test_idle_ttl_reap_and_expired_vs_not_found():
    store = ResultStore(ttl_s=0.05)
    store.put(_result())
    time.sleep(0.1)
    assert store.reap() == 1
    assert store.get("r-1") is None
    assert store.status_of_missing("r-1") == "expired"     # AD-38
    assert store.status_of_missing("never-existed") == "not_found"
    # tombstone: a late merge against the reaped id is rejected, not resurrected
    assert store.mutate("r-1", lambda e: None) is False


def test_idle_ttl_resets_on_access():
    store = ResultStore(ttl_s=0.15)
    store.put(_result())
    for _ in range(4):                          # keep touching within TTL
        time.sleep(0.05)
        assert store.get("r-1") is not None
    assert store.reap() == 0                    # AD-28: idle-based, not creation-based


# ---------------------------------------------------------------- queue --

@pytest.fixture
def q():
    store = ResultStore()
    queue = JobQueue(store, workers=2, bound=2, watchdog_interval_s=0.05)
    yield store, queue
    queue.shutdown()


def test_job_runs_to_done_and_settles(q):
    store, queue = q
    store.put(_result())
    ran = threading.Event()
    assert queue.submit("r-1", "second-engine-check", ran.set) == PENDING
    assert _wait(lambda: store.get("r-1").jobs["second-engine-check"].state == DONE)
    assert ran.is_set()
    body = store.get("r-1").public()
    assert body["settled"] is True and body["pending"] == []


def test_exactly_one_terminal_state_on_exception(q):
    store, queue = q

    def boom():
        raise RuntimeError("layer exploded")

    store.put(_result())
    queue.submit("r-1", "warning-reread", boom)
    assert _wait(lambda: store.get("r-1").jobs["warning-reread"].state == FAILED)
    job = store.get("r-1").jobs["warning-reread"]
    assert "layer exploded" in (job.error or "")
    assert store.get("r-1").public()["settled"] is True


def test_queue_full_sheds_at_submit(q):
    store, queue = q
    store.put(_result())
    gate = threading.Event()
    # fill both workers + occupy the bound (bound=2)
    assert queue.submit("r-1", "a", gate.wait) == PENDING
    assert queue.submit("r-1", "b", gate.wait) == PENDING
    assert queue.submit("r-1", "c", lambda: None) == SHED   # AD-27 shed-at-submit
    assert store.get("r-1").jobs["c"].state == SHED         # visible immediately (AD-13)
    gate.set()
    assert _wait(lambda: store.get("r-1").public()["settled"])


def test_cancel_terminates_pending_and_blocks_late_completion(q):
    store, queue = q
    store.put(_result())
    gate = threading.Event()
    queue.submit("r-1", "a", gate.wait)
    assert queue.cancel_result("r-1") is True
    assert store.get("r-1").jobs["a"].state == CANCELLED
    # tombstone: late mutations are rejected...
    assert store.mutate("r-1", lambda e: None) is False
    gate.set()
    time.sleep(0.1)
    # ...and the job's own completion cannot overwrite the terminal state
    assert store.get("r-1").jobs["a"].state == CANCELLED
    assert queue.cancel_result("r-1") is True               # idempotent


def test_watchdog_forces_timed_out(q):
    store, queue = q
    store.put(_result())
    queue.submit("r-1", "slow", lambda: time.sleep(3), deadline_s=0.1)
    assert _wait(lambda: store.get("r-1").jobs["slow"].state == TIMED_OUT, 2.0)
    assert store.get("r-1").public()["settled"] is True     # AD-27 server-side


# ------------------------------------------------------------- app-level --

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api import main as appmod
    # plain client (no context manager) skips startup: no paddle warm
    return TestClient(appmod.app), appmod


def test_healthz_schema(client):
    c, appmod = client
    body = c.get("/healthz").json()
    assert body["state"] in ("ready", "loading", "down")    # AD-40
    assert set(body["queue"]) == {"depth", "oldest_age_s"}
    assert "rss_mb" in body and "ready" in body


def test_verify_get_unknown_vs_expired_codes(client):
    c, appmod = client
    assert c.get("/api/verify/nope").json()["code"] == "not_found"
    appmod.store.put(_result("gone-1"))
    appmod.store._ttl_s = 0.0
    appmod.store.reap()
    appmod.store._ttl_s = 3600.0
    r = c.get("/api/verify/gone-1")
    assert r.status_code == 404 and r.json()["code"] == "expired"


def test_verify_get_and_cancel_flow(client):
    c, appmod = client
    entry = appmod.store.put(_result("live-1"))
    body = c.get("/api/verify/live-1").json()
    assert body["settled"] is True and body["result_id"] == "live-1"
    assert "cancel_token" not in body                       # AD-39: POST-only
    r = c.post("/api/verify/live-1/cancel", data={"token": "wrong"})
    assert r.status_code == 403 and r.json()["code"] == "bad_token"
    r = c.post("/api/verify/live-1/cancel", data={"token": entry.cancel_token})
    assert r.status_code == 409 and r.json()["code"] == "already_settled"


def test_healthz_live_while_verify_blocks(client):
    """N1 exit criterion: /healthz answers while a slow verify is in flight
    (sync-def endpoints run in the threadpool, never on the event loop)."""
    c, appmod = client

    class SlowFake:
        def ready(self):
            return True

        def extract(self, path):
            time.sleep(1.5)
            return []

    real = appmod.extractor
    appmod.extractor = SlowFake()
    try:
        import io

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (400, 400), "white").save(buf, "JPEG")
        results = {}

        def do_verify():
            results["verify"] = c.post(
                "/api/verify",
                files={"image": ("l.jpg", buf.getvalue(), "image/jpeg")},
                data={"application": "{}"})

        t = threading.Thread(target=do_verify)
        t.start()
        time.sleep(0.3)                          # verify is mid-extract
        t0 = time.perf_counter()
        r = c.get("/healthz")
        healthz_ms = (time.perf_counter() - t0) * 1000
        t.join(timeout=10)
        assert r.status_code == 200
        assert healthz_ms < 500, f"healthz blocked {healthz_ms:.0f}ms"
        assert results["verify"].status_code == 200
        body = results["verify"].json()
        assert body["settled"] is True and body["status"] == "settled"
        assert body["pending"] == [] and "cancel_token" in body  # AD-34/39
    finally:
        appmod.extractor = real


def test_rollup_recomputed_on_every_read():
    """The J-layers mutate fields after the provisional envelope froze its
    rollup — found live as a clean golden settling 'mismatch_found' (the
    provisional warning read was red; J2 fixed the FIELD but not the
    summary). public() must recompute screening/attention from the fields
    it returns."""
    store = ResultStore()
    r = _result()
    r["fields"] = [{"field": "government_warning", "status": "MISMATCH"}]
    r["screening_result"] = "mismatch_found"
    entry = store.put(r)
    assert entry.public()["screening_result"] == "mismatch_found"
    entry.result["fields"][0]["status"] = "MATCH"     # what merge_refinement does
    body = entry.public()
    assert body["screening_result"] == "no_mismatch_found"
    assert body["attention_state"] == "none"
