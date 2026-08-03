"""Public-exposure guards for the deployed URL (TODOS P1 prerequisites).

Loopback-only deployments never hit these defaults; the moment the app
fronts a real network the knobs are env-driven:

- LABELCHECK_RATE_RPM       verify requests/min per client IP (default 30)
- LABELCHECK_MAX_INFLIGHT   concurrent verifies before shedding (default 4)
- LABELCHECK_ALLOWED_HOSTS  comma list for Host validation (AD-31);
                            default covers loopback + TestClient

stdlib only, in-process (AD-25 single-worker invariant makes per-process
state correct by construction).
"""

from __future__ import annotations

import os
import threading
import time


def allowed_hosts() -> list[str]:
    raw = os.environ.get("LABELCHECK_ALLOWED_HOSTS",
                         "localhost,127.0.0.1,testserver")
    return [h.strip() for h in raw.split(",") if h.strip()]


class RateLimiter:
    """Token bucket per client IP. Monotonic clock; buckets are pruned so
    an internet-facing deployment can't grow memory unboundedly."""

    def __init__(self, rpm: int | None = None, burst: int | None = None,
                 max_clients: int = 10_000):
        self.rpm = rpm if rpm is not None else int(
            os.environ.get("LABELCHECK_RATE_RPM", "30"))
        self.burst = burst if burst is not None else max(5, self.rpm // 3)
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, t)
        self._max_clients = max_clients
        self._lock = threading.Lock()

    def allow(self, ip: str) -> tuple[bool, float]:
        """Returns (allowed, retry_after_s)."""
        if self.rpm <= 0:                      # 0 disables the limiter
            return True, 0.0
        now = time.monotonic()
        rate = self.rpm / 60.0
        with self._lock:
            tokens, t = self._buckets.get(ip, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - t) * rate)
            if tokens >= 1.0:
                self._buckets[ip] = (tokens - 1.0, now)
                allowed, wait = True, 0.0
            else:
                self._buckets[ip] = (tokens, now)
                allowed, wait = False, (1.0 - tokens) / rate
            if len(self._buckets) > self._max_clients:
                # drop the stalest half; correctness is per-IP fairness, not
                # perfect memory of every client ever seen
                stale = sorted(self._buckets.items(), key=lambda kv: kv[1][1])
                for ip_, _ in stale[: len(stale) // 2]:
                    del self._buckets[ip_]
        return allowed, round(wait, 1)


class InflightGate:
    """Shed verifies beyond a concurrency cap with 429 + Retry-After — the
    fast-path pool must never build an invisible queue (same posture as the
    job queue's shed-at-submit)."""

    def __init__(self, limit: int | None = None):
        self.limit = limit if limit is not None else int(
            os.environ.get("LABELCHECK_MAX_INFLIGHT", "4"))
        self._count = 0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            if self._count >= self.limit:
                return False
            self._count += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._count -= 1

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._count
