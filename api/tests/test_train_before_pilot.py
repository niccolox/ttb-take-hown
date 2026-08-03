"""Train-before-pilot plumbing (docs/research/train-before-pilot.md):
the curated training set rides /api/samples, and the local-only UI
telemetry endpoint accepts exactly the allowlisted events."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from fastapi.testclient import TestClient

from api import main


def test_training_set_is_five_ordered_lessons():
    client = TestClient(main.app)
    rows = client.get("/api/samples").json()
    training = sorted((r for r in rows if r.get("training")),
                      key=lambda r: r["training"][0])
    assert [r["training"][0] for r in training] == [1, 2, 3, 4, 5]
    assert all(r["training"][1].startswith("Lesson") for r in training)
    # the five lessons cover: clean pass, real defect, rules knowledge,
    # front+back pair, honest degradation
    assert {r["id"] for r in training} == {"clean_match", "obvious_mismatch",
                                           "table_wine_no_abv", "wine_blur",
                                           "bad_photo"}


def test_ui_telemetry_allowlist(tmp_path, monkeypatch):
    from api import layers
    monkeypatch.setattr(layers, "TELEMETRY_PATH", tmp_path / "e4.jsonl")
    client = TestClient(main.app)
    ok = client.post("/api/telemetry", json={"event": "tour_completed", "ms": 90000})
    assert ok.status_code == 200
    assert (tmp_path / "e4.jsonl").exists()
    line = (tmp_path / "e4.jsonl").read_text()
    assert '"tour_completed"' in line and '"ms": 90000' in line
    # free text and unknown events never land in the stream
    assert client.post("/api/telemetry", json={"event": "drop table"}).status_code == 400
    assert client.post("/api/telemetry", json={"note": "hi"}).status_code == 400
    # oversized/negative ms is discarded, event still recorded
    ok2 = client.post("/api/telemetry", json={"event": "tour_started", "ms": -5})
    assert ok2.status_code == 200
    assert '"ms"' not in (tmp_path / "e4.jsonl").read_text().splitlines()[-1]
