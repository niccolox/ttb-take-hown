"""Weight-contrast heuristic plumbing tests on rendered strips.

NOTE (kill-gate): synthetic renders smoke-test the PLUMBING only — they do not
VALIDATE the heuristic (PLAN.md Rev 2.1: validation requires printed-and-
photographed samples). These tests assert directional behavior and the
conservative unknown path.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.rules.contrast import weight_contrast

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def strip(prefix_bold: bool, body_bold: bool):
    img = Image.new("L", (900, 120), 255)
    d = ImageDraw.Draw(img)
    pf = ImageFont.truetype(FONT_B if prefix_bold else FONT, 26)
    bf = ImageFont.truetype(FONT_B if body_bold else FONT, 26)
    d.text((10, 10), "GOVERNMENT WARNING:", font=pf, fill=0)
    d.text((10, 60), "According to the Surgeon General women should not drink", font=bf, fill=0)
    prefix_box = (10, 5, 360, 45)
    body_box = (10, 55, 880, 100)
    return np.array(img), prefix_box, body_box


def test_bold_prefix_regular_body_is_ok():
    outcome, detail = weight_contrast(*strip(True, False))
    assert outcome == "ok", detail


def test_all_bold_never_passes():
    # Safety property (kill-gate contract): equal weight must NEVER read "ok".
    # Asserting the violation ("no_contrast") requires printed-photo validation;
    # "unknown" (→ confirm visually) is the acceptable conservative outcome.
    outcome, detail = weight_contrast(*strip(True, True))
    assert outcome != "ok", detail


def test_all_regular_never_passes():
    outcome, detail = weight_contrast(*strip(False, False))
    assert outcome != "ok", detail


def test_empty_region_is_unknown():
    img = np.full((120, 900), 255, dtype=np.uint8)
    outcome, _ = weight_contrast(img, (10, 5, 360, 45), (10, 55, 880, 100))
    assert outcome == "unknown"


def test_blur_gate_never_asserts_violation():
    """Gaussian blur widens strokes past the thin floor while erasing the
    bold delta — a blurred region must return unknown, never no_contrast
    (the gw_wine_blur false-red regression)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    img = Image.new("L", (600, 200), 255)
    d = ImageDraw.Draw(img)
    try:
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        reg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        import pytest
        pytest.skip("dejavu fonts unavailable")
    d.text((10, 10), "GOVERNMENT WARNING:", font=bold, fill=0)
    for i in range(4):
        d.text((10, 50 + i * 34), "consumption of alcoholic beverages impairs", font=reg, fill=0)
    blurred = np.array(img.filter(ImageFilter.GaussianBlur(2.2)))
    outcome, detail = weight_contrast(blurred, (10, 10, 320, 40), (10, 50, 590, 190))
    assert outcome == "unknown"
    assert "blur" in detail.lower()
    # and the sharp version still measures normally (not gated)
    sharp = np.array(img)
    outcome2, _ = weight_contrast(sharp, (10, 10, 320, 40), (10, 50, 590, 190))
    assert outcome2 != "unknown" or "blur" not in _.lower()
