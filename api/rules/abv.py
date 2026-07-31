"""ABV parsing and the three-band comparison (PLAN.md Rev 2.1).

Bands are magnitude heuristics from 27 CFR (§4.36, §5.65(c), §7.65(c));
the legal warrant for tolerating any drift is Form 5100.31 allowable-revision
item 11. Exact → MATCH; within band → WITHIN_TOLERANCE (amber, never green);
outside band or across a class boundary → MISMATCH.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class BevType(str, Enum):
    WINE = "wine"
    SPIRITS = "distilled_spirits"
    MALT = "malt_beverage"
    UNSPECIFIED = "unspecified"


class AbvVerdict(str, Enum):
    MATCH = "MATCH"
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    MISMATCH = "MISMATCH"
    NOT_REQUIRED = "NOT_REQUIRED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class AbvReading:
    percent: float | None = None
    proof: float | None = None
    range_lo: float | None = None
    range_hi: float | None = None
    raw: str = ""


_PCT = r"(\d{1,2}(?:\.\d{1,2})?)"
RANGE_RE = re.compile(rf"(?:ALC(?:OHOL)?\.?\s*)?{_PCT}\s*%?\s*TO\s*{_PCT}\s*%", re.I)
PCT_RE = re.compile(
    rf"(?:ALC(?:OHOL)?\.?\s*)?{_PCT}\s*%\s*(?:ALC(?:OHOL)?\.?)?\s*(?:/|BY)?\s*(?:VOL(?:UME)?\.?)?"
    rf"|ALC(?:OHOL)?\.?\s*{_PCT}\s*(?:%|PERCENT)", re.I)
PROOF_RE = re.compile(rf"{_PCT}\s*PROOF", re.I)


def parse_abv(text: str) -> AbvReading:
    r = AbvReading(raw=text)
    if m := RANGE_RE.search(text):
        r.range_lo, r.range_hi = float(m.group(1)), float(m.group(2))
        return r
    if m := PROOF_RE.search(text):
        r.proof = float(m.group(1))
    if m := PCT_RE.search(text):
        r.percent = float(m.group(1) or m.group(2))
    elif r.proof is not None:
        r.percent = r.proof / 2.0  # proof-only label, converted for comparison
    return r


def band(bev: BevType, labeled: float) -> float:
    """Tolerance band, selected by the LABEL-stated value (Rev 2.1 F3)."""
    if bev == BevType.WINE:
        return 1.0 if labeled > 14.0 else 1.5
    if bev in (BevType.SPIRITS, BevType.MALT):
        return 0.3
    return 0.3  # UNSPECIFIED → strictest


# wine tax-class breaks (27 CFR; tolerance never crosses these)
WINE_BREAKS = (14.0, 21.0, 24.0)


def crosses_class_boundary(bev: BevType, a: float, b: float) -> bool:
    lo, hi = sorted((a, b))
    if bev == BevType.WINE:
        return any(lo <= brk < hi for brk in WINE_BREAKS)
    if bev == BevType.MALT:
        # 0.5% floor and the 2.5% low-alcohol cap are un-rescuable lines
        return any(lo < brk <= hi for brk in (0.5, 2.5))
    return False


def compare_abv(app_percent: float | None, label: AbvReading, bev: BevType,
                *, digit_confidence_ok: bool = True) -> tuple[AbvVerdict, str]:
    """Three-band comparison. `digit_confidence_ok` is the OCR digit-confidence
    gate (Rev 2.1 F6b): a within-band result on shaky digits is NEEDS_REVIEW."""
    if app_percent is None:
        return AbvVerdict.NEEDS_REVIEW, "no application ABV supplied"

    if label.range_lo is not None:
        inside = label.range_lo <= app_percent <= label.range_hi
        if inside:
            return AbvVerdict.WITHIN_TOLERANCE, (
                f"label states a range {label.range_lo}%–{label.range_hi}%; "
                f"application {app_percent}% falls inside — confirm")
        return AbvVerdict.MISMATCH, "application value outside the labeled range"

    if label.percent is None:
        return AbvVerdict.NEEDS_REVIEW, "no ABV located on label (disposition is commodity-aware upstream)"

    diff = abs(label.percent - app_percent)
    if diff < 1e-9:
        return AbvVerdict.MATCH, "exact match"

    if crosses_class_boundary(bev, label.percent, app_percent):
        return AbvVerdict.MISMATCH, "difference crosses a regulatory class boundary — no tolerance applies"

    b = band(bev, label.percent)
    if diff <= b + 1e-9:
        if not digit_confidence_ok:
            return AbvVerdict.NEEDS_REVIEW, "within band but OCR digit confidence low — check the crop"
        note = (f"label {label.percent}% vs application {app_percent}% — within ±{b} "
                f"(magnitude per 27 CFR; drift permitted by allowable-revision item 11) — confirm")
        return AbvVerdict.WITHIN_TOLERANCE, note
    return AbvVerdict.MISMATCH, f"label {label.percent}% vs application {app_percent}% exceeds ±{b}"


def proof_consistency(label: AbvReading) -> tuple[bool | None, str]:
    """Label-internal ABV↔proof cross-check (proof = 2×ABV, §5.65(b))."""
    if label.percent is None or label.proof is None:
        return None, "label does not state both percent and proof"
    ok = abs(label.proof - 2.0 * label.percent) <= 0.2
    return ok, (f"{label.percent}% vs {label.proof} proof "
                + ("consistent" if ok else "INCONSISTENT (proof should be 2×ABV)"))


def abv_required(bev: BevType, label_class_type: str | None) -> tuple[bool, str]:
    """Commodity-aware requiredness (Rev 2.1). Wine optionality is conditional on
    the label's class/type carrying 'table'/'light' (§4.36(a)); malt optionality
    depends on facts the tool cannot know → confirm, never silent."""
    if bev == BevType.SPIRITS:
        return True, "mandatory for distilled spirits (§5.63(a)(3))"
    if bev == BevType.WINE:
        ct = (label_class_type or "").casefold()
        if "table" in ct or "light" in ct:
            return False, 'optional: "table"/"light" wine designation present (§4.36(a))'
        return True, "required unless designated table/light wine ≤14% (§4.36(a))"
    if bev == BevType.MALT:
        return False, "not required federally unless flavored-alcohol applies — confirm (§7.63(a)(3); state law may differ)"
    return True, "commodity not specified — treated as required (strictest)"
