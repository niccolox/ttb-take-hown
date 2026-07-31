"""Weight-contrast heuristic for the GOVERNMENT WARNING prefix (§16.22(a)(2)).

Three-outcome model (PLAN.md Rev 2.1): 'ok' | 'no_contrast' | 'unknown'.
Measures median stroke width (distance-transform on binarized ink) of the
prefix region vs the statement body ON THE SAME LABEL — a relative, same-
image comparison (absolute thresholds are confounded by font/size/blur).

Conservative by design: anything ambiguous → 'unknown' ("confirm visually").
No side ever passes from this heuristic alone; per-direction validation on
printed-and-photographed samples is the M0 kill-gate (synthetic renders are
excluded from *validating* the heuristic — they only smoke-test the plumbing).
"""

from __future__ import annotations

import numpy as np

try:
    import cv2
except ImportError:                                    # pragma: no cover
    cv2 = None

# ratio bands (prefix stroke / body stroke), height-normalized
OK_RATIO = 1.22          # clear bold-vs-regular contrast
NO_CONTRAST_RATIO = 1.08 # essentially equal weight → violation (side indeterminate)
MIN_INK_PIXELS = 150     # below this, measurement is meaningless → unknown


def _median_stroke(gray: np.ndarray) -> tuple[float, float] | None:
    """Median stroke width (px) and text height proxy for a text region."""
    if gray.size == 0:
        return None
    # Otsu on inverted (ink = white); guard flat regions
    if float(gray.std()) < 8:
        return None
    # Upscale small text before measuring: JPEG + Otsu quantization flattens
    # sub-2px stroke differences (observed on 17px type at quality 75).
    if gray.shape[0] < 220:
        gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(255 - gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = binary > 0
    if int(ink.sum()) < MIN_INK_PIXELS:
        return None
    dist = cv2.distanceTransform((ink * 255).astype(np.uint8), cv2.DIST_L2, 3)
    strokes = dist[ink]
    # stroke width ≈ 2 × median distance-to-background of ink pixels
    width = 2.0 * float(np.median(strokes[strokes > 0])) if (strokes > 0).any() else 0.0
    # glyph height = median connected-component height (NOT region extent —
    # a multi-line body region would otherwise report paragraph height)
    n, _, stats, _ = cv2.connectedComponentsWithStats((ink * 255).astype(np.uint8), 8)
    heights = [stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, n)
               if stats[i, cv2.CC_STAT_AREA] >= 8]
    height = float(np.median(heights)) if heights else 0.0
    if width <= 0 or height <= 0:
        return None
    return width, height


def weight_contrast(image_gray: np.ndarray,
                    prefix_box: tuple[float, float, float, float],
                    body_box: tuple[float, float, float, float]) -> tuple[str, str]:
    """Returns (outcome, detail). Outcome ∈ {'ok','no_contrast','unknown'}."""
    if cv2 is None:
        return "unknown", "OpenCV unavailable — weight not measured."

    def crop(box):
        x1, y1, x2, y2 = (int(max(0, v)) for v in box)
        return image_gray[y1:y2, x1:x2]

    p = _median_stroke(crop(prefix_box))
    b = _median_stroke(crop(body_box))
    if p is None or b is None:
        return "unknown", "Too little ink in the measured regions — confirm visually."

    (pw, ph), (bw, bh) = p, b
    # Guard: if the regions' text heights differ wildly, stroke widths aren't
    # comparable (different font sizes) → unknown. All-caps vs mixed-case
    # height differences (~25%) pass this guard.
    if ph <= 0 or bh <= 0 or max(ph, bh) / min(ph, bh) > 1.6:
        return "unknown", "Prefix and body text sizes differ too much to compare weight — confirm visually."
    # Raw stroke-width ratio: same-size regions, so weight is the dominant signal.
    # (Height normalization was tried and rejected: caps-vs-mixed-case height
    # bias inflates the ratio ~1.3x at equal weight.)
    ratio = pw / bw if bw > 0 else 0.0
    detail = f"stroke-width ratio prefix/body = {ratio:.2f}"
    if ratio >= OK_RATIO:
        return "ok", detail + " — heading reads bolder than the body."
    if ratio <= NO_CONTRAST_RATIO:
        return "no_contrast", detail + " — no weight contrast between heading and body."
    return "unknown", detail + " — ambiguous; confirm visually."
