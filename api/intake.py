"""S0 intake: deskew (PLAN-enrichment N2).

Neither engine deskews for us (research: NVIDIA's stack has no orientation
normalization anywhere; paddle's textline classifier flips 90°/180° but
does not fix small in-plane skew). A cheap Hough-based estimate + one
rotation before OCR fixes the photo_skew reading-order scramble for BOTH
engines at the one place it belongs.

Coordinate contract: rotation (expand=True) changes the image frame, but
evidence crops draw on the CLIENT'S ORIGINAL bitmap. `SkewTransform`
carries the inverse mapping — verify boxes go rotated-frame → pre-rotation
frame here, then through the existing `scale_back` resize factor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

# Rotate only when the estimate is confident and meaningful: below 1.5° the
# engines cope and rotation just blurs; above 30° it's more likely a sideways
# photo (a different failure class) than label skew.
MIN_ANGLE_DEG = 1.5
MAX_ANGLE_DEG = 30.0
_EST_WIDTH = 800          # estimation runs on a downscale; cheap and stable
_MIN_LINES = 5            # fewer near-horizontal lines than this → no signal


def estimate_skew_deg(gray: np.ndarray) -> float:
    """Median angle of near-horizontal Hough lines, degrees. Positive =
    the text tilts counter-clockwise on screen (PIL's rotate direction
    with y-down coordinates makes `img.rotate(-angle)` the correction —
    the sign is pinned by tests, not convention)."""
    import cv2

    h, w = gray.shape[:2]
    if w > _EST_WIDTH:
        r = _EST_WIDTH / w
        gray = cv2.resize(gray, (int(w * r), int(h * r)))
        h, w = gray.shape[:2]
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=int(w * 0.25), maxLineGap=8)
    if lines is None:
        return 0.0
    angles = []
    for (x1, y1, x2, y2), in lines:
        if x2 == x1:
            continue
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if a > 90:
            a -= 180
        elif a < -90:
            a += 180
        if abs(a) <= MAX_ANGLE_DEG:
            angles.append(a)
    if len(angles) < _MIN_LINES:
        return 0.0
    # image y grows downward, so a visually-CCW tilt measures negative here;
    # flip so the return value is the visual (CCW-positive) skew
    return -float(np.median(angles))


@dataclass
class SkewTransform:
    """Inverse mapping for boxes from the rotated frame back to the
    pre-rotation frame (both at the same resize scale)."""
    angle_deg: float                 # rotation applied via img.rotate(-angle)
    pre_size: tuple[int, int]        # (w, h) before rotation
    rot_size: tuple[int, int]        # (w, h) after rotation (expand=True)

    def box_to_pre(self, box: list[float]) -> list[float]:
        x1, y1, x2, y2 = box
        cx_r, cy_r = self.rot_size[0] / 2, self.rot_size[1] / 2
        cx_p, cy_p = self.pre_size[0] / 2, self.pre_size[1] / 2
        # img.rotate(-angle) rotates content by -angle (screen CCW = +angle
        # in y-down coords); undo = rotate corner vectors by -angle in
        # y-down coords about the center
        t = math.radians(-self.angle_deg)
        cos, sin = math.cos(t), math.sin(t)
        xs, ys = [], []
        for px, py in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            dx, dy = px - cx_r, py - cy_r
            xs.append(cx_p + dx * cos - dy * sin)
            ys.append(cy_p + dx * sin + dy * cos)
        return [min(xs), min(ys), max(xs), max(ys)]


def deskew(img: Image.Image) -> tuple[Image.Image, SkewTransform | None]:
    """Estimate and correct in-plane skew. Returns the (possibly) rotated
    image and the transform for mapping boxes back — None when no rotation
    was applied."""
    gray = np.asarray(img.convert("L"))
    angle = estimate_skew_deg(gray)
    if not (MIN_ANGLE_DEG < abs(angle) <= MAX_ANGLE_DEG):
        return img, None
    pre_size = img.size
    rotated = img.rotate(-angle, resample=Image.BICUBIC, expand=True,
                         fillcolor=(255, 255, 255))
    return rotated, SkewTransform(angle_deg=angle, pre_size=pre_size,
                                  rot_size=rotated.size)
