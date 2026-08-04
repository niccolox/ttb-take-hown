"""Shared fixtures. The app's per-IP rate limiter is real and shared across
TestClient calls — enough POST-heavy tests in one suite run trip it (found
as an ordering-dependent failure). Every test gets a fresh permissive
limiter; the limiter's own behavior is tested explicitly in test_ratelimit."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))


@pytest.fixture(autouse=True)
def _permissive_rate_limiter(monkeypatch):
    if "api.main" in sys.modules:
        from api.ratelimit import RateLimiter
        import api.main as main
        monkeypatch.setattr(main, "rate_limiter",
                            RateLimiter(rpm=1_000_000, burst=1_000_000))
    yield
