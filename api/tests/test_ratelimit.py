"""Public-exposure guard tests: token bucket, inflight shedding, Host
validation, and the verify endpoint's 429 contract."""

from __future__ import annotations

import threading
import time

from api.ratelimit import InflightGate, RateLimiter


def test_bucket_allows_burst_then_limits():
    rl = RateLimiter(rpm=60, burst=3)
    assert all(rl.allow("1.2.3.4")[0] for _ in range(3))
    ok, retry = rl.allow("1.2.3.4")
    assert not ok and retry > 0


def test_bucket_refills_over_time():
    rl = RateLimiter(rpm=6000, burst=1)          # 100 tokens/s → fast test
    assert rl.allow("ip")[0]
    assert not rl.allow("ip")[0]
    time.sleep(0.02)
    assert rl.allow("ip")[0]


def test_buckets_are_per_ip():
    rl = RateLimiter(rpm=60, burst=1)
    assert rl.allow("a")[0]
    assert not rl.allow("a")[0]
    assert rl.allow("b")[0]                      # different client unaffected


def test_zero_rpm_disables():
    rl = RateLimiter(rpm=0)
    assert all(rl.allow("x")[0] for _ in range(100))


def test_client_pruning_bounds_memory():
    rl = RateLimiter(rpm=60, burst=1, max_clients=10)
    for i in range(50):
        rl.allow(f"ip-{i}")
    assert len(rl._buckets) <= 10


def test_inflight_gate_sheds_and_releases():
    g = InflightGate(limit=2)
    assert g.acquire() and g.acquire()
    assert not g.acquire()                       # at capacity → shed
    g.release()
    assert g.acquire()
    g.release(); g.release()
    assert g.inflight == 0


def _client():
    from fastapi.testclient import TestClient

    from api import main as appmod
    return TestClient(appmod.app), appmod


def test_host_validation_rejects_unknown_host():
    c, _ = _client()
    r = c.get("/healthz", headers={"Host": "evil.example.com"})
    assert r.status_code == 400                  # AD-31 TrustedHost


def test_verify_returns_429_when_at_capacity():
    c, appmod = _client()

    class Ready:
        def ready(self):
            return True

        def extract(self, path):
            return []

    real_extractor = appmod.extractor
    real_gate = appmod.inflight_gate
    appmod.extractor = Ready()
    from api.ratelimit import InflightGate as IG
    appmod.inflight_gate = IG(limit=0)           # everything sheds
    try:
        r = c.post("/api/verify", files={"image": ("l.jpg", b"x", "image/jpeg")},
                   data={"application": "{}"})
        assert r.status_code == 429
        assert r.json()["code"] == "busy" and "Retry-After" in r.headers
    finally:
        appmod.extractor = real_extractor
        appmod.inflight_gate = real_gate


def test_verify_returns_429_when_rate_limited():
    c, appmod = _client()
    from api.ratelimit import RateLimiter as RL
    real = appmod.rate_limiter
    appmod.rate_limiter = RL(rpm=60, burst=1)
    try:
        first = c.post("/api/verify", files={"image": ("l.jpg", b"x", "image/jpeg")},
                       data={"application": "{}"})
        assert first.status_code != 429          # burst token spent (may 4xx later in pipeline)
        second = c.post("/api/verify", files={"image": ("l.jpg", b"x", "image/jpeg")},
                        data={"application": "{}"})
        assert second.status_code == 429
        assert second.json()["code"] == "rate_limited"
        assert int(second.headers["Retry-After"]) >= 1
    finally:
        appmod.rate_limiter = real
