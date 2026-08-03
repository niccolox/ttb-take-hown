"""Wine-specific label statements beyond the shared fields (part 4 audit,
docs/research/wine-labeling-audit-ttb.md): sulfite declaration (§4.32(e)),
name-and-address phrase (§4.35), standards of fill (§4.72). All presence/
legality checks — never identity matches — and every failure lands amber:
the waiver (sulfites) and exemptions (saké fill) are invisible to a photo.
"""

from __future__ import annotations

import re

# "Sulphites" is an authorized alternative spelling (TTB sulfite guidance)
SULFITE_RE = re.compile(r"\bSUL(?:F|PH)ITES?\b", re.I)

# §4.35 mandatory phrase family: BOTTLED/PACKED BY (domestic), IMPORTED BY
# (imports). Optional descriptive prefixes (Produced and…, Vinted and…)
# still contain the mandatory verb, so matching the core phrase suffices.
# BREWED/CANNED cover malt's optional phrases (§7.66 — where the phrase
# itself is optional, so callers treat absence differently per commodity).
NAME_ADDRESS_RE = re.compile(r"\b(?:BOTTLED|PACKED|IMPORTED|BREWED|CANNED)\s+BY\b", re.I)

# §4.72 authorized standards of fill (mL). 4–17 L must be even liters;
# ≥18 L (and saké) are exempt from the standards entirely.
WINE_FILL_ML = (3000.0, 2250.0, 1800.0, 1500.0, 1000.0, 750.0, 720.0, 700.0,
                620.0, 600.0, 568.0, 550.0, 500.0, 473.0, 375.0, 360.0, 355.0,
                330.0, 300.0, 250.0, 200.0, 187.0, 180.0, 100.0, 50.0)


def varietal_percentages(lines: list[str], varietals: list[str]) -> list[float] | None:
    """Percentages printed with the named varieties ('60% CHARDONNAY') —
    §4.23(d): when two or more varieties designate the wine, each percentage
    must be shown and they must total 100. Returns one value per varietal, or
    None unless EVERY named varietal carries a printed percentage (a partial
    read proves nothing)."""
    vals: list[float] = []
    for v in varietals:
        pat = re.compile(rf"(\d{{1,3}}(?:\.\d+)?)\s*%\s*{re.escape(v)}", re.I)
        hit = next((m for t in lines if (m := pat.search(t))), None)
        if hit is None:
            return None
        vals.append(float(hit.group(1)))
    return vals


def wine_fill_authorized(ml: float, tol_ml: float = 1.0) -> tuple[bool, str]:
    """Is this volume an authorized wine standard of fill? ±1 mL matches the
    repo's practical net-contents tolerance (unit-conversion rounding)."""
    if ml >= 18000.0:
        return True, "18 L or more — exempt from standards of fill (§4.72)"
    if 4000.0 <= ml < 18000.0:
        if abs(ml / 1000.0 - round(ml / 1000.0)) * 1000.0 <= tol_ml:
            return True, "4–17 L stated in even liters (§4.72)"
        return False, "4–17 L containers must be filled in even liters (§4.72)"
    if any(abs(ml - std) <= tol_ml for std in WINE_FILL_ML):
        return True, "authorized standard of fill (§4.72)"
    return False, (f"{ml:g} mL is not an authorized wine standard of fill "
                   "(§4.72; saké and ≥18 L containers are exempt)")
