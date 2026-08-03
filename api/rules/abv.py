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


_PCT = r"\b(\d{1,2}(?:\.\d{1,2})?)"   # \b stops "100% AGAVE" matching as "00%"
# range separator accepts "TO" and hyphen/dash — TTB's own §4.36 examples are
# hyphenated ("17%-19% ALC. BY VOL."); TO-only parsing read those as a
# specific 17% and compared against the wrong number
RANGE_RE = re.compile(rf"(?:ALC(?:OHOL)?\.?\s*)?{_PCT}\s*%?\s*(?:TO|[-–—])\s*{_PCT}\s*%", re.I)
PCT_RE = re.compile(
    rf"(?:ALC(?:OHOL)?\.?\s*)?{_PCT}\s*%\s*(?:ALC(?:OHOL)?\.?)?\s*(?:/|BY)?\s*(?:VOL(?:UME)?\.?)?"
    rf"|ALC(?:OHOL)?\.?\s*{_PCT}\s*(?:%|PERCENT)", re.I)
# proof needs 3 digits (80-151 proof spirits are routine); \b stops "101" matching as "01"
_PROOF_NUM = r"(\d{1,3}(?:\.\d{1,2})?)"
PROOF_RE = re.compile(rf"\b{_PROOF_NUM}\s*PROOF", re.I)

# a percent line is the ABV statement only when it carries alcohol context —
# varietal percentages ('60% CHARDONNAY', §4.23(d)) and blend prose are also
# percent lines and hijacked the first-match locator on TTB's own BAM c10
# sample labels (false MISMATCH on approvable three-piece/designated-brand
# formats). Callers prefer a context line, falling back to any percent line.
ABV_CONTEXT_RE = re.compile(r"ALC|VOL|PROOF", re.I)


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
        # malt beverages may not state alcohol content as a range or as
        # max/min values at all (§7.65(b), TTB malt-ABV guidance) — the
        # statement itself is the defect, whatever the application says
        if bev == BevType.MALT:
            return AbvVerdict.MISMATCH, (
                f"label states a range {label.range_lo}%–{label.range_hi}% — alcohol "
                "content on malt beverages may not be expressed as a range or "
                "max/min (§7.65(b))")
        # wine range statements carry their own legality limits (§4.36(b),
        # TTB wine-ABV guidance): the span may not exceed 2 points above 14%
        # or 3 points at/below, and a range may never overlap a class/tax-
        # grade limit — an illegal range is a labeling defect regardless of
        # whether the application value falls inside it
        if bev == BevType.WINE:
            if crosses_class_boundary(bev, label.range_lo, label.range_hi):
                return AbvVerdict.MISMATCH, (
                    f"labeled range {label.range_lo}%–{label.range_hi}% overlaps a wine "
                    "class/tax-grade limit (14/21/24%) — a range may not cross one (§4.36(b))")
            cap = 2.0 if label.range_lo > 14.0 else 3.0
            span = label.range_hi - label.range_lo
            if span > cap + 1e-9:
                return AbvVerdict.MISMATCH, (
                    f"labeled range spans {span:g} points — wine ranges may not exceed "
                    f"{cap:g} points for this class (§4.36(b))")
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


_ABV_ABBREV_RE = re.compile(r"\bA\.?\s?B\.?\s?V\.?\b", re.I)
_ABW_ABBREV_RE = re.compile(r"\bA\.?\s?B\.?\s?W\.?\b", re.I)
_OVERPRECISE_RE = re.compile(r"(\d+\.\d{2,})\s*%")


def abv_format_legality(label_text: str | None, bev: BevType) -> tuple[str, str] | None:
    """Statement-wording check for wine (§4.36(a)) and malt (§7.65(b)):
    only 'alc.' and 'vol.' may abbreviate — 'ABV' is not permitted on
    either; malt additionally bans 'ABW' and requires expression to the
    nearest 0.1% at 0.5%+ ABV. Wording is a labeling defect, not a data
    mismatch, so callers escalate green to amber at most. None = no opinion
    (spirits wording is not asserted here)."""
    if bev not in (BevType.WINE, BevType.MALT) or not label_text:
        return None
    cite = "§4.36(a)" if bev == BevType.WINE else "§7.65(b)"
    if _ABV_ABBREV_RE.search(label_text):
        return ("FAIL", f"'ABV' is not a permitted abbreviation — only 'alc.' "
                        f"and 'vol.' may abbreviate ({cite})")
    if bev == BevType.MALT:
        if _ABW_ABBREV_RE.search(label_text):
            return ("FAIL", "'ABW' is not a permitted abbreviation for alcohol "
                            "by weight (§7.65(b)(1))")
        m = _OVERPRECISE_RE.search(label_text)
        if m and float(m.group(1)) >= 0.5:
            return ("FAIL", f"{m.group(1)}% — malt alcohol content must be "
                            "stated to the nearest 0.1% at 0.5%+ ABV (§7.65(b)(2))")
    return ("PASS", "statement wording uses permitted forms")


def abv_required(bev: BevType, label_class_type: str | None) -> tuple[bool, str]:
    """Commodity-aware requiredness (Rev 2.1). Wine optionality is conditional on
    the label's class/type carrying 'table'/'light' (§4.36(a)); malt optionality
    depends on facts the tool cannot know → confirm, never silent."""
    if bev == BevType.SPIRITS:
        return True, "mandatory for distilled spirits (§5.63(a)(3))"
    if bev == BevType.WINE:
        ct = (label_class_type or "").casefold()
        # word-boundary, not substring: 'Moonlight Cellars' / 'Twilight
        # Zinfandel' must not read as a light-wine designation (BAM c10 audit)
        if re.search(r"\b(?:table|light)\b", ct):
            return False, 'optional: "table"/"light" wine designation present (§4.36(a))'
        return True, "required unless designated table/light wine ≤14% (§4.36(a))"
    if bev == BevType.MALT:
        return False, "not required federally unless flavored-alcohol applies — confirm (§7.63(a)(3); state law may differ)"
    return True, "commodity not specified — treated as required (strictest)"
