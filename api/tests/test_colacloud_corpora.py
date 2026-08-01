"""Integrity tests over the COLA Cloud–generated eval corpora.

These run against whatever the pipelines have pulled into api/eval/colacloud/
(gitignored — COLA Cloud assets are not redistributed), so every test skips
cleanly when a corpus is absent: on a fresh clone the module is a no-op; on a
machine that has run the pipelines it verifies the generated manifests and
images are exactly what the UI and verifier expect.

Set LABELCHECK_OCR_EVAL=1 to also run one full front+back verification per
corpus through the real OCR pipeline (slow — model load + inference).
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.eval.colacloud_pipeline import TYPES

COLACLOUD = Path(__file__).parents[1] / "eval" / "colacloud"

CORPORA = sorted(d.name for d in COLACLOUD.iterdir()
                 if d.is_dir() and (d / "manifest.json").exists()) if COLACLOUD.exists() else []

pytestmark = pytest.mark.skipif(
    not CORPORA, reason="no COLA Cloud corpora pulled (api/eval/colacloud/ is gitignored)")

VALID_PANELS = {"front", "back", "main", "unknown"}
VALID_BEV = {"wine", "malt_beverage", "distilled_spirits"}


def _manifest(name):
    return json.loads((COLACLOUD / name / "manifest.json").read_text())


@pytest.mark.parametrize("corpus", CORPORA)
def test_manifest_schema(corpus):
    entries = _manifest(corpus)
    assert entries, f"{corpus}: empty manifest"
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), f"{corpus}: duplicate TTB IDs"
    for e in entries:
        assert e["id"].isdigit() and len(e["id"]) == 14, f"{corpus}/{e['id']}: bad TTB ID"
        app = e["application"]
        assert app["beverage_type"] in VALID_BEV
        assert app["beverage_type"] == TYPES[corpus][1]
        assert app["brand_name"], f"{corpus}/{e['id']}: registry pull must carry a brand"
        if app.get("alcohol_content"):
            assert app["alcohol_content"].endswith("%")
        assert e["provenance"]["ttb_id"] == e["id"]
        assert "COLA" in e["provenance"]["source"] or "Registry" in e["provenance"]["source"]


@pytest.mark.parametrize("corpus", CORPORA)
def test_panel_files_on_disk(corpus):
    d = COLACLOUD / corpus
    for e in _manifest(corpus):
        files = e.get("files") or [{"file": e["file"], "panel": "front"}]
        assert files[0]["file"] == e["file"], \
            f"{corpus}/{e['id']}: entry['file'] must be the first (front) panel"
        panels = [f["panel"] for f in files]
        assert len(panels) == len(set(panels)), f"{corpus}/{e['id']}: duplicate panel"
        for f in files:
            assert f["panel"] in VALID_PANELS
            p = d / f["file"]
            assert p.exists() and p.stat().st_size > 0, f"missing/empty {p}"
            assert f["file"].startswith(e["id"]), \
                f"{corpus}/{f['file']}: panel file must be named after its TTB ID"


@pytest.mark.parametrize("corpus", CORPORA)
def test_no_orphan_images(corpus):
    """Every image on disk is referenced by the manifest — orphans mean a pull
    died before its incremental save, and recover_orphans should be run."""
    d = COLACLOUD / corpus
    entries = _manifest(corpus)
    referenced = {e["file"] for e in entries}
    for e in entries:
        referenced.update(f["file"] for f in e.get("files") or [])
    on_disk = {p.name for p in list(d.glob("*.jpg")) + list(d.glob("*.png"))}
    assert on_disk <= referenced, f"{corpus}: orphaned images {sorted(on_disk - referenced)}"


@pytest.mark.parametrize("corpus", CORPORA)
def test_registry_block(corpus):
    for e in _manifest(corpus):
        reg = e.get("registry")
        assert reg, f"{corpus}/{e['id']}: missing registry block (run --backfill-registry)"
        assert "serial_number" not in reg   # applicant serial not exposed by the API
        assert reg.get("brand_name") == e["application"]["brand_name"]
        for k, v in reg.items():
            assert v not in (None, "", [], "N/A"), f"{corpus}/{e['id']}: empty registry.{k}"


@pytest.mark.parametrize("corpus", CORPORA)
def test_images_decode(corpus):
    from PIL import Image
    d = COLACLOUD / corpus
    for e in _manifest(corpus):
        for f in e.get("files") or [{"file": e["file"]}]:
            with Image.open(d / f["file"]) as img:
                img.verify()                       # corrupt files raise
            with Image.open(d / f["file"]) as img:
                assert img.width >= 100 and img.height >= 100, \
                    f"{corpus}/{f['file']}: implausibly small label image"


@pytest.mark.skipif(not os.environ.get("LABELCHECK_OCR_EVAL"),
                    reason="set LABELCHECK_OCR_EVAL=1 for the slow OCR pass")
@pytest.mark.parametrize("corpus", CORPORA)
def test_ocr_verify_one_per_corpus(corpus):
    """Full pipeline over one front+back entry per corpus: the envelope must be
    schema-valid and every status a legal one. Registry ground truth means
    verdicts should be matches or honest reviews — this asserts the contract
    shape, not per-field outcomes (real photos keep their right to amber)."""
    import numpy as np
    from PIL import Image

    from api.extractor import PaddleExtractor
    from api.verify import verify_multi

    d = COLACLOUD / corpus
    entry = _manifest(corpus)[0]
    files = entry.get("files") or [{"file": entry["file"], "panel": "front"}]

    ex = PaddleExtractor()
    panels = []
    for f in files:
        img = Image.open(d / f["file"]).convert("RGB")
        if max(img.size) > 2000:
            r = 2000 / max(img.size)
            img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        tmp = d / "_test_tmp.jpg"
        img.save(tmp, "JPEG", quality=92)
        if not panels:
            ex.warm(str(tmp))
        panels.append((ex.extract(str(tmp)), np.array(img.convert("L"))))
    tmp.unlink(missing_ok=True)

    result = verify_multi(panels, entry["application"])
    assert result["screening_result"] in (
        "no_mismatch_found", "mismatch_found", "screening_incomplete")
    legal = {"MATCH", "LIKELY_MATCH", "WITHIN_TOLERANCE", "MISMATCH",
             "NEEDS_REVIEW", "NOT_CHECKED", "NOT_REQUIRED"}
    assert result["fields"], "no fields verified"
    for f in result["fields"]:
        assert f["status"] in legal
        if f.get("evidence") and len(files) > 1:
            assert f["evidence"]["panel"] in range(len(files))
