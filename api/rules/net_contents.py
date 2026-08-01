"""Net contents parsing with unit conversion (PLAN.md: 750 mL, 0.75 L, 25.4 fl oz;
±1 mL practical tolerance adopted from competitor survey, documented)."""

from __future__ import annotations

import re

ML_PER = {"ml": 1.0, "milliliter": 1.0, "milliliters": 1.0,
          "cl": 10.0, "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0,
          "fl oz": 29.5735, "floz": 29.5735, "oz": 29.5735, "pint": 473.176, "pt": 473.176}

NET_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ML|MILLILITERS?|CL|L|LITERS?|LITRES?|FL\.?\s*OZ\.?|OZ\.?|PINTS?|PT)\b",
    re.I)


def parse_net_ml(text: str) -> float | None:
    total = 0.0
    found = False
    # handle compound e.g. "1 PINT 0.9 FL. OZ."
    for m in NET_RE.finditer(text):
        val = float(m.group(1))
        unit = re.sub(r"[.\s]+", " ", m.group(2).lower()).strip()
        unit = {"fl oz": "fl oz", "floz": "fl oz", "oz": "fl oz",
                "pints": "pint", "pt": "pint"}.get(unit, unit)
        unit = unit.rstrip("s") if unit in ("liters", "milliliters") else unit
        factor = ML_PER.get(unit) or ML_PER.get(unit.rstrip("s"))
        if factor:
            total += val * factor
            found = True
    return round(total, 1) if found else None


def compare_net(app_text: str | None, label_text: str | None, tol_ml: float = 1.0):
    """Returns (verdict, note): 'MATCH' | 'MISMATCH' | 'NEEDS_REVIEW' | 'NOT_CHECKED'."""
    if not app_text:
        return "NOT_CHECKED", "no application value entered"
    app_ml = parse_net_ml(app_text)
    if app_ml is None:
        return "NEEDS_REVIEW", f'could not parse application value "{app_text}"'
    if not label_text:
        return "NEEDS_REVIEW", "net contents not located (commodity-aware disposition upstream: may be molded in glass for spirits/malt)"
    lab_ml = parse_net_ml(label_text)
    if lab_ml is None:
        return "NEEDS_REVIEW", f'could not parse label text "{label_text}"'
    if abs(lab_ml - app_ml) <= tol_ml:
        note = "exact match" if abs(lab_ml - app_ml) < 1e-9 else \
            f"{label_text} ≈ {app_text} (±{tol_ml} mL practical tolerance, documented)"
        return "MATCH", note
    return "MISMATCH", f"label {lab_ml} mL vs application {app_ml} mL"
