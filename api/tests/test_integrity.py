"""Model-weight integrity tests (supply-chain P1): manifest round-trip,
tamper detection, environment-artifact tolerance."""

from __future__ import annotations

from pathlib import Path

from api.integrity import PINNED_MODELS, check, emit, hash_model_dir


def _fake_models(root: Path) -> Path:
    for name in PINNED_MODELS:
        d = root / name
        d.mkdir(parents=True)
        (d / "inference.pdiparams").write_bytes(b"weights-" + name.encode())
        (d / "inference.yml").write_text("cfg: 1\n")
    return root


def test_emit_then_check_passes(tmp_path):
    models = _fake_models(tmp_path / "models")
    manifest = tmp_path / "models.sha256"
    manifest.write_text(emit(models))
    assert check(models, manifest) == []


def test_tampered_weights_fail(tmp_path):
    models = _fake_models(tmp_path / "models")
    manifest = tmp_path / "models.sha256"
    manifest.write_text(emit(models))
    victim = models / PINNED_MODELS[0] / "inference.pdiparams"
    victim.write_bytes(victim.read_bytes() + b"\x00")     # single-byte flip
    problems = check(models, manifest)
    assert len(problems) == 1 and PINNED_MODELS[0] in problems[0]
    assert "mismatch" in problems[0]


def test_missing_model_dir_fails(tmp_path):
    models = _fake_models(tmp_path / "models")
    manifest = tmp_path / "models.sha256"
    manifest.write_text(emit(models))
    import shutil
    shutil.rmtree(models / PINNED_MODELS[1])
    problems = check(models, manifest)
    assert any(PINNED_MODELS[1] in p for p in problems)


def test_env_artifacts_do_not_affect_digest(tmp_path):
    """paddlex download bookkeeping differs per install and must be
    invisible to the pin (verified against real local-vs-docker drift)."""
    models = _fake_models(tmp_path / "models")
    d = models / PINNED_MODELS[0]
    before = hash_model_dir(d)
    (d / "CACHEDIR.TAG").write_text("cache tag")
    (d / "inference.pdiparams.metadata").write_text('{"mtime": 12345}')
    (d / "inference.pdiparams.lock").write_text("")
    assert hash_model_dir(d) == before


def test_committed_manifest_matches_local_models():
    """The repo's manifest must verify against this machine's models (the
    known-good source it was emitted from). Skips when models absent."""
    import pytest

    from api.integrity import DEFAULT_MANIFEST, default_models_dir
    models = default_models_dir()
    if not all((models / n).exists() for n in PINNED_MODELS):
        pytest.skip("pinned paddle models not installed here")
    assert check(models, DEFAULT_MANIFEST) == []
