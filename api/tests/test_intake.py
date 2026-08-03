"""S0 deskew tests (N2): sign conventions pinned against PIL's actual
rotation, box round-trip through the real transform, and the photo_skew
golden as the engine-free acceptance signal."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from api.intake import MIN_ANGLE_DEG, SkewTransform, deskew, estimate_skew_deg

GOLDEN = Path(__file__).parent.parent / "eval" / "golden"


def _text_like(w=900, h=600) -> Image.Image:
    """White page with horizontal dark bars — text-line stand-ins that give
    Hough plenty of near-horizontal edges."""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    for y in range(80, h - 60, 60):
        d.rectangle([60, y, w - 60, y + 18], fill="black")
    return img


def test_straight_image_is_left_alone():
    img = _text_like()
    out, tf = deskew(img)
    assert tf is None and out is img
    assert abs(estimate_skew_deg(np.asarray(img.convert("L")))) < MIN_ANGLE_DEG


def test_estimate_sign_and_magnitude():
    img = _text_like()
    # PIL rotate(+4) turns content visually counter-clockwise
    rotated = img.rotate(4, resample=Image.BICUBIC, expand=True,
                         fillcolor=(255, 255, 255))
    est = estimate_skew_deg(np.asarray(rotated.convert("L")))
    assert 3.0 <= est <= 5.0, f"expected ~+4 CCW, got {est}"
    clockwise = img.rotate(-4, resample=Image.BICUBIC, expand=True,
                           fillcolor=(255, 255, 255))
    est_cw = estimate_skew_deg(np.asarray(clockwise.convert("L")))
    assert -5.0 <= est_cw <= -3.0, f"expected ~-4 CW, got {est_cw}"


def test_deskew_corrects_to_near_zero():
    img = _text_like()
    rotated = img.rotate(6, resample=Image.BICUBIC, expand=True,
                         fillcolor=(255, 255, 255))
    fixed, tf = deskew(rotated)
    assert tf is not None and 5.0 <= tf.angle_deg <= 7.0
    residual = estimate_skew_deg(np.asarray(fixed.convert("L")))
    assert abs(residual) < 1.0, f"residual skew {residual}"


def test_box_round_trip_through_real_rotation():
    """A box found in the rotated frame must map back onto the original
    square's location (the evidence-coordinate round-trip)."""
    img = Image.new("RGB", (800, 500), "white")
    d = ImageDraw.Draw(img)
    true_box = (300, 200, 380, 260)
    d.rectangle(true_box, fill="black")
    angle = 5.0
    rotated = img.rotate(-angle, resample=Image.BICUBIC, expand=True,
                         fillcolor=(255, 255, 255))   # what deskew() applies
    tf = SkewTransform(angle_deg=angle, pre_size=img.size,
                       rot_size=rotated.size)
    arr = np.asarray(rotated.convert("L"))
    ys, xs = np.where(arr < 100)
    found = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
    back = tf.box_to_pre(found)
    # rotated-rect hull is slightly larger than the true box; it must
    # CONTAIN the true box and stay close
    assert back[0] <= true_box[0] + 2 and back[1] <= true_box[1] + 2
    assert back[2] >= true_box[2] - 2 and back[3] >= true_box[3] - 2
    for got, want in zip(back, true_box):
        assert abs(got - want) < 12, f"round-trip drifted: {back} vs {true_box}"


def test_photo_skew_golden_yields_signal():
    """Engine-free acceptance: the estimator must produce a stable, bounded
    answer on the skewed golden (exact angle isn't pinned — the golden's
    skew is photographic, not synthetic)."""
    img = Image.open(GOLDEN / "photo_skew.jpg").convert("RGB")
    a1 = estimate_skew_deg(np.asarray(img.convert("L")))
    a2 = estimate_skew_deg(np.asarray(img.convert("L")))
    assert a1 == a2, "estimator must be deterministic"
    assert abs(a1) <= 30.0
    out, tf = deskew(img)
    if tf is not None:                       # rotation applied → must reduce skew
        residual = estimate_skew_deg(np.asarray(out.convert("L")))
        assert abs(residual) <= abs(a1)
