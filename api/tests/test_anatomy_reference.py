"""TTB Anatomy-of-a-Wine-Label reference case (api/eval/anatomy/).

The interactive tool's image map — stacked clickable slices wired to TTB's
own element explanations — ingested as an eval asset (ingest_anatomy.py).
These tests pin the asset's integrity and the mapping onto this tool's
field model; set LABELCHECK_OCR_EVAL=1 to also run the stitched front+back
panels through the real OCR pipeline (TTB's reference label must screen
with no mismatch).
"""

import json
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[2]))

ROOT = Path(__file__).parents[1] / "eval" / "anatomy"
REF = json.loads((ROOT / "reference.json").read_text())

# what the label actually says — the COLA application for the e2e run
APPLICATION = {"beverage_type": "wine", "brand_name": "LIGHTHOUSE",
               "fanciful_name": "Stormchaser White",
               "class_type": "Chardonnay", "appellation": "Hudson River Region",
               "vintage": "2018", "alcohol_content": "13.5%",
               "net_contents": "750 mL"}


def test_slices_match_reference_geometry():
    for s in REF["slices"]:
        p = ROOT / s["file"]
        assert p.exists(), s["file"]
        assert Image.open(p).size == (s["w"], s["h"]), s["file"]
    # slices tile their panel exactly: total slice area == panel area
    for panel in ("front", "back"):
        area = sum(s["w"] * s["h"] for s in REF["slices"] if s["panel"] == panel)
        pw, ph = REF["panels"][panel]["width"], REF["panels"][panel]["height"]
        assert area <= pw * ph                       # gaps allowed (flex padding)
        assert area >= pw * ph - 4 * pw              # ...but only the 4px seam
        assert Image.open(ROOT / f"{panel}.png").size == (pw, ph)


def test_every_interactive_slice_maps_to_a_known_element():
    keys = {s["element"] for s in REF["slices"] if s["element"]}
    assert keys == set(REF["elements"])              # no orphan hotspots, no unused elements


def test_element_fields_exist_in_the_verifier_model():
    known = {"brand_name", "fanciful_name", "class_type", "appellation", "vintage",
             "name_address", "government_warning", "sulfite_declaration",
             "net_contents", "alcohol_content"}
    mapped = {e["field"] for e in REF["elements"].values() if e["field"]}
    assert mapped == known                           # TTB's regulated elements ⊆ our fields
    # the unmapped elements are exactly the ones TTB marks optional/unregulated
    unmapped = {k for k, e in REF["elements"].items() if not e["field"]}
    assert unmapped == {"imageLH", "addInfo", "web", "UPC"}


def test_mandatory_elements_carry_ttb_text():
    for key, e in REF["elements"].items():
        assert e["ttb_text"], key                    # every element kept its explanation


def test_vertical_words_do_not_bridge_lines():
    """Rotated UPC digits (5×67 px) beside the warning made the y-tolerance
    their own height and chain-collapsed five warning lines into one
    scrambled mega-line on this reference label. Vertical-aspect words must
    be isolated, never merged into (or seeding) horizontal lines."""
    from api.locator import Locator, Word
    rows = [Word(t, (10 + i * 60, y, 60 + i * 60, y + 12), 0.95)
            for y in (300, 316, 332, 348)
            for i, t in enumerate(["AAA", "BBB", "CCC"])]
    upc = Word("12345", (200, 296, 205, 363), 0.95)         # tall, skinny, spans all rows
    lines = Locator([*rows, upc]).lines
    texts = [l.text for l in lines]
    assert texts.count("AAA BBB CCC") == 4                  # rows stay distinct
    assert "12345" in texts                                 # isolated, not absorbed


def test_side_column_stays_out_of_the_warning_block():
    """The isolated UPC lines sit mid-block by y-order; block growth must
    skip lines with no horizontal overlap with the anchor — without breaking
    row adjacency across the skip."""
    from api.locator import Locator, Word
    from api.rules.warning import STATUTORY_WARNING

    import textwrap
    words, y = [], 300
    for row in textwrap.wrap(STATUTORY_WARNING, 46):
        x = 30
        for t in row.split():
            words.append(Word(t, (x, y, x + len(t) * 5, y + 12), 0.95)); x += len(t) * 5 + 4
        y += 16
    words.append(Word("12345", (310, 320, 315, 400), 0.95))  # vertical UPC column
    loc = Locator(words)
    text = loc.find_warning().text
    assert "12345" not in text
    assert "HEALTH PROBLEMS" in text.upper()


# ── distilled spirits (2024 tool, api/eval/anatomy_spirits/) ─────────────────

DS_ROOT = Path(__file__).parents[1] / "eval" / "anatomy_spirits"
DS_REF = json.loads((DS_ROOT / "reference.json").read_text())

# what TTB's spirits reference label actually says (specialty product:
# the statement of composition serves as the class/type designation)
DS_APPLICATION = {"beverage_type": "distilled_spirits",
                  "brand_name": "CAPTAIN JOHN'S",
                  "fanciful_name": "Spiced Rum",
                  "class_type": "Rum With Natural Flavors Added",
                  "alcohol_content": "20%", "net_contents": "750 mL"}


def test_ds_slices_match_reference_geometry():
    for s in DS_REF["slices"]:
        p = DS_ROOT / s["file"]
        assert p.exists() and Image.open(p).size == (s["w"], s["h"]), s["file"]
    for panel in ("front", "back"):
        area = sum(s["w"] * s["h"] for s in DS_REF["slices"] if s["panel"] == panel)
        pw, ph = DS_REF["panels"][panel]["width"], DS_REF["panels"][panel]["height"]
        assert area == pw * ph                       # spirits rows tile exactly
        assert Image.open(DS_ROOT / f"{panel}.png").size == (pw, ph)


def test_ds_hotspots_and_field_mapping():
    keys = {s["element"] for s in DS_REF["slices"] if s["element"]}
    assert keys == set(DS_REF["elements"])
    mapped = {e["field"] for e in DS_REF["elements"].values() if e["field"]}
    assert mapped == {"brand_name", "fanciful_name", "class_type",
                      "alcohol_content", "net_contents", "government_warning"}
    # unmapped = TTB's optional/unregulated elements + nameAddress, which is
    # deliberately unmapped until the part 5 audit lands
    unmapped = {k for k, e in DS_REF["elements"].items() if not e["field"]}
    assert unmapped == {"GPI", "nameAddress", "webAdd", "addInfo", "upcBar"}
    for key, e in DS_REF["elements"].items():
        assert e["ttb_text"], key


@pytest.mark.skipif(not os.environ.get("LABELCHECK_OCR_EVAL"),
                    reason="set LABELCHECK_OCR_EVAL=1 for the slow OCR e2e")
def test_ds_reference_label_screens_clean_end_to_end():
    import numpy as np
    from api.extractor import PaddleExtractor
    from api.verify import verify_multi

    ex = PaddleExtractor()
    ex.warm(str(DS_ROOT / "front.png"))
    panels = []
    for panel in ("front", "back"):
        img = Image.open(DS_ROOT / f"{panel}.png").convert("RGB")
        panels.append((ex.extract(np.asarray(img)), np.asarray(img.convert("L"))))
    r = verify_multi(panels, DS_APPLICATION)
    assert r["screening_result"] != "mismatch_found"
    # at the tool's 325px width the warning body is below the contrast
    # measurement floor → an HONEST amber (weight_contrast_suspect) is the
    # expected disposition; the wording itself must verify
    warn = next(f for f in r["fields"] if f["field"] == "government_warning")
    subs = {s["check"]: s["outcome"] for s in (warn.get("sub_results") or [])}
    assert subs.get("text_exact") == "pass"


@pytest.mark.skipif(not os.environ.get("LABELCHECK_OCR_EVAL"),
                    reason="set LABELCHECK_OCR_EVAL=1 for the slow OCR e2e")
def test_ttb_reference_label_screens_clean_end_to_end():
    """TTB's own reference label through the real pipeline: front + back →
    no mismatch. (The definitive 'we screen what TTB teaches' check.)"""
    import numpy as np
    from api.extractor import PaddleExtractor
    from api.verify import verify_multi

    ex = PaddleExtractor()
    ex.warm(str(ROOT / "front.png"))
    panels = []
    for panel in ("front", "back"):
        img = Image.open(ROOT / f"{panel}.png").convert("RGB")
        words = ex.extract(np.asarray(img))
        panels.append((words, np.asarray(img.convert("L"))))
    r = verify_multi(panels, APPLICATION)
    assert r["screening_result"] != "mismatch_found"
