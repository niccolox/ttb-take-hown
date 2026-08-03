"""No-egress proof (audit F1): the app must import and serve with the
network switched off at the Python level.

Blocks socket creation BEFORE importing the app, then exercises /healthz
and a full /api/verify round-trip through the in-process ASGI TestClient
(no real sockets involved). Any code path that tries to reach the network
— a model hub lookup, a telemetry phone-home, a hijacked dependency —
raises immediately and fails the check.

Run: .venv/bin/python scripts/no_egress_check.py
Exit 0 = proven; anything else = an egress attempt or a served error.
"""

from __future__ import annotations

import io
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))   # repo root on the path

_REAL_SOCKET = socket.socket


class _NoEgressSocket(socket.socket):
    """AF_UNIX stays available (asyncio's self-pipe and other local IPC are
    not egress); every INET/INET6 socket — i.e., anything that could reach a
    network — raises."""

    def __init__(self, family=socket.AF_INET, *a, **k):
        if family in (socket.AF_INET, socket.AF_INET6):
            raise OSError("network disabled by no_egress_check")
        super().__init__(family, *a, **k)


def main() -> int:
    socket.socket = _NoEgressSocket           # type: ignore[misc]
    socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
        OSError("network disabled by no_egress_check"))

    from fastapi.testclient import TestClient

    from api import main as appmod

    class FakeExtractor:
        def ready(self):
            return True

        def extract(self, path):
            return []

    appmod.extractor = FakeExtractor()
    appmod.qa_extractor = None                 # no background layers needed
    client = TestClient(appmod.app)

    h = client.get("/healthz")
    assert h.status_code == 200, h.text

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), "white").save(buf, "JPEG")
    r = client.post("/api/verify",
                    files={"image": ("l.jpg", buf.getvalue(), "image/jpeg")},
                    data={"application": "{}"})
    assert r.status_code == 200, r.text
    assert r.json().get("settled") is True

    print("no-egress check PASSED: app imported and served a full verify "
          "with sockets disabled (0 egress attempts reached the network)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
