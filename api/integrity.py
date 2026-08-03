"""Model-weight integrity pinning (TODOS P1, ai-supply-chain research).

The Dockerfile bakes OCR models by letting paddlex download them from
Baidu's CDN at build time — with no integrity check, a CDN compromise
ships silently. This module records/asserts SHA-256 over the three model
dirs the extractor pins.

Usage:
    python -m api.integrity emit  [--models-dir DIR]          > api/models.sha256
    python -m api.integrity check [--models-dir DIR] [MANIFEST]

Checked at two points: the Dockerfile (post-bake, build fails on
mismatch) and `PaddleExtractor.warm` (startup fails loud, never a silent
compliance verdict from tampered weights).
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

# exactly the dirs extractor.py pins — a paddle bump that changes the model
# set must change this list AND the manifest in the same commit
PINNED_MODELS = ("PP-OCRv5_server_det", "en_PP-OCRv5_mobile_rec",
                 "PP-LCNet_x1_0_textline_ori")
DEFAULT_MANIFEST = Path(__file__).parent / "models.sha256"


def default_models_dir() -> Path:
    env = os.environ.get("LABELCHECK_MODELS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".paddlex" / "official_models"


# paddlex writes per-environment download bookkeeping next to the weights;
# these legitimately differ between installs and carry no model content
_ENV_ARTIFACTS = {"CACHEDIR.TAG"}
_ENV_SUFFIXES = (".metadata", ".lock")


def _is_model_content(p: Path) -> bool:
    return p.name not in _ENV_ARTIFACTS and not p.name.endswith(_ENV_SUFFIXES)


def hash_model_dir(model_dir: Path) -> str:
    """One digest per model dir: sha256 over (relative path, file sha256)
    pairs in sorted order — stable across copies, mtimes, and paddlex's
    per-environment download metadata."""
    outer = hashlib.sha256()
    files = sorted(p for p in model_dir.rglob("*")
                   if p.is_file() and _is_model_content(p))
    if not files:
        raise FileNotFoundError(f"no files under {model_dir}")
    for p in files:
        inner = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                inner.update(chunk)
        outer.update(str(p.relative_to(model_dir)).encode())
        outer.update(inner.hexdigest().encode())
    return outer.hexdigest()


def emit(models_dir: Path) -> str:
    return "".join(f"{hash_model_dir(models_dir / name)}  {name}\n"
                   for name in PINNED_MODELS)


def check(models_dir: Path, manifest_path: Path = DEFAULT_MANIFEST) -> list[str]:
    """Returns a list of problems; empty list = verified."""
    problems = []
    try:
        expected = dict(reversed(line.split()) for line in
                        manifest_path.read_text().strip().splitlines())
    except OSError as e:
        return [f"manifest unreadable: {e}"]
    for name in PINNED_MODELS:
        want = expected.get(name)
        if want is None:
            problems.append(f"{name}: missing from manifest")
            continue
        try:
            got = hash_model_dir(models_dir / name)
        except (OSError, FileNotFoundError) as e:
            problems.append(f"{name}: unreadable ({e})")
            continue
        if got != want:
            problems.append(f"{name}: SHA-256 mismatch — weights differ from "
                            f"the pinned known-good build")
    return problems


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else "check"
    models_dir = default_models_dir()
    if "--models-dir" in args:
        models_dir = Path(args[args.index("--models-dir") + 1])
    if mode == "emit":
        sys.stdout.write(emit(models_dir))
    elif mode == "check":
        rest = [a for i, a in enumerate(args[1:], 1)
                if a != "--models-dir" and args[i - 1] != "--models-dir"]
        manifest = Path(rest[0]) if rest else DEFAULT_MANIFEST
        problems = check(models_dir, manifest)
        if problems:
            print("MODEL INTEGRITY FAIL:", *problems, sep="\n  ", file=sys.stderr)
            sys.exit(1)
        print(f"model integrity OK ({len(PINNED_MODELS)} dirs)")
    else:
        print(f"unknown mode {mode!r} (emit|check)", file=sys.stderr)
        sys.exit(2)
