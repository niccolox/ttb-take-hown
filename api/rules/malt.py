"""Malt-beverage label statements (part 7 audit,
docs/research/malt-labeling-audit-ttb.md): prohibited sulfite-free claims,
the aspartame declaration, and net-contents form (§7.70 US standard
measures). Same posture as the wine module: presence/legality checks that
land amber at worst — composition facts (actual ppm, aspartame content)
are invisible to a photo.
"""

from __future__ import annotations

import re

# TTB does not permit negative sulfite claims on malt beverages
# ("sulfite free", "free of sulfites", "contains no sulfites")
SULFITE_FREE_RE = re.compile(
    r"\bSUL(?:F|PH)ITE[-\s]?FREE\b|\bFREE\s+OF\s+SUL(?:F|PH)ITES\b"
    r"|\b(?:CONTAINS\s+)?NO\s+SUL(?:F|PH)ITES\b", re.I)

# aspartame declaration (§7.63(b)(4)): required wording, CAPITAL letters
ASPARTAME_HINT_RE = re.compile(r"PHENYLKETONURIC|PHENYLALANINE|ASPARTAME", re.I)
ASPARTAME_STMT_RE = re.compile(
    r"PHENYLKETONURICS:?\s+CONTAINS\s+PHENYLALANINE")   # case-sensitive on purpose

_US_UNIT_RE = re.compile(r"\bFL\.?\s*OZ\.?|\bOZ\.?\b|\bPINTS?\b|\bPT\.?\b"
                         r"|\bQUARTS?\b|\bQTS?\.?\b|\bGAL(?:LON)?S?\b", re.I)
_METRIC_RE = re.compile(r"\d\s*(?:ML|MILLILITERS?|CL|L|LITERS?|LITRES?)\b", re.I)


def aspartame_check(line_texts: list[str]) -> tuple[str, str] | None:
    """Fires only when the label mentions aspartame/phenylalanine at all —
    absence proves nothing about the product. When present, the declaration
    must read PHENYLKETONURICS: CONTAINS PHENYLALANINE in capital letters."""
    hit = next((t for t in line_texts if ASPARTAME_HINT_RE.search(t)), None)
    if hit is None:
        return None
    if ASPARTAME_STMT_RE.search(hit):
        return ("MATCH", "Aspartame declaration present in the required form.")
    return ("NEEDS_REVIEW",
            "Aspartame-related text found, but not the required capital-letter "
            'statement "PHENYLKETONURICS: CONTAINS PHENYLALANINE." — inspect '
            f'the label (found: "{hit.strip()[:60]}").')


def malt_net_form(label_text: str, ml: float | None) -> tuple[str, str] | None:
    """§7.70: malt net contents must be stated in US standard measures —
    metric may accompany but never replace them — and exact pint/quart/
    gallon volumes must be stated as such (TTB's own example: a 16 fl oz
    container must say '1 Pint'). Returns (reason_code, message) or None."""
    has_us = bool(_US_UNIT_RE.search(label_text))
    if not has_us and _METRIC_RE.search(label_text):
        return ("metric_only_net", "stated only in metric — malt beverages must "
                "use US standard measures; metric may accompany, not replace "
                "them (§7.70)")
    if ml is None or not has_us:
        return None
    for target, name, token in ((473.176, "1 pint", r"\bPINTS?\b|\bPT\.?\b"),
                                (946.353, "1 quart", r"\bQUARTS?\b|\bQTS?\.?\b"),
                                (3785.41, "1 gallon", r"\bGAL(?:LON)?S?\b")):
        if abs(ml - target) <= 1.0 and not re.search(token, label_text, re.I):
            return ("net_form", f"this volume must be stated as {name}, not in "
                    f"fluid ounces (§7.70)")
    return None
