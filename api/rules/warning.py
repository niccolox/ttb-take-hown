"""Government warning validator (PLAN.md: three sub-results; Rev 2.1 weight-contrast model).

Statutory constant provenance: 27 CFR §16.21, verbatim from eCFR (as of 2026-07-01).
Format rules: §16.22 (caps+bold prefix; body NOT bold; type-size matrix not
checkable from photos — reported as informational citations).
A checksum test (tests/test_warning.py) guards editorial drift of the constant.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum

from .normalize import whitespace_only

STATUTORY_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)
STATUTORY_SOURCE = "27 CFR 16.21 (eCFR, current as of 2026-07-01)"

PREFIX_CAPS_RE = re.compile(r"GOVERNMENT\s*WARNING\s*:")          # case-sensitive
PREFIX_ANY_RE = re.compile(r"government\s*warning\s*:?", re.I)


class SubCheck(str, Enum):
    TEXT = "text_exact"
    PREFIX_CAPS = "prefix_caps"
    WEIGHT_CONTRAST = "weight_contrast"


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNVERIFIABLE = "unverifiable"
    NOT_FOUND = "not_found"


@dataclass
class WarningResult:
    outcomes: dict[SubCheck, Outcome]
    details: dict[SubCheck, str]
    diff_tokens: list[tuple[str, str]] = field(default_factory=list)  # (op, token)
    citation: str = STATUTORY_SOURCE
    confusable_punct: bool = False  # deviation is comma↔period glyphs only


def word_diff(expected: str, found: str) -> list[tuple[str, str]]:
    """Word-level diff after whitespace-only normalization. Tokens match
    case-insensitively: §16.21 prescribes the WORDS; capitals are mandated only
    for the "GOVERNMENT WARNING:" heading (§16.22(a)(2)), which the separate
    prefix_caps sub-check enforces on raw OCR. All-caps bodies are common and
    compliant — 'ACCORDING' vs 'According' is not a wording deviation."""
    e, f = whitespace_only(expected).split(), whitespace_only(found).split()
    ec, fc = [t.casefold() for t in e], [t.casefold() for t in f]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ec, fc).get_opcodes():
        if op == "equal":
            out.extend(("equal", t) for t in e[i1:i2])
        else:
            out.extend(("expected", t) for t in e[i1:i2])
            out.extend(("found", t) for t in f[j1:j2])
    return out


def plain_sentence(diff: list[tuple[str, str]]) -> str:
    """One plain sentence for the first deviation (UI spec: never a raw diff)."""
    exp = [t for op, t in diff if op == "expected"]
    fnd = [t for op, t in diff if op == "found"]
    if not exp and not fnd:
        return "The label's warning text matches the required text."
    if fnd and exp:
        return f'The label says "{fnd[0]}" where the required text says "{exp[0]}".'
    if exp:
        return f'The required word "{exp[0]}" is missing from the label\'s warning.'
    return f'The label\'s warning contains extra text: "{fnd[0]}".'


def validate_warning(extracted_verbatim: str | None,
                     *, region_quality_ok: bool = True,
                     weight_contrast: str = "unknown") -> WarningResult:
    """`extracted_verbatim` is the raw, case-preserved OCR text of the warning
    region (verbatim by construction — the local-OCR premise). `weight_contrast`
    comes from the stroke-width heuristic: 'ok' | 'no_contrast' | 'unknown'
    (three-outcome model, Rev 2.1 — no side ever passes from the heuristic alone).
    """
    outcomes: dict[SubCheck, Outcome] = {}
    details: dict[SubCheck, str] = {}
    confusable_punct = False

    if not extracted_verbatim or not PREFIX_ANY_RE.search(extracted_verbatim):
        outcomes[SubCheck.TEXT] = Outcome.NOT_FOUND
        outcomes[SubCheck.PREFIX_CAPS] = Outcome.NOT_FOUND
        outcomes[SubCheck.WEIGHT_CONTRAST] = Outcome.UNVERIFIABLE
        details[SubCheck.TEXT] = ("Government warning not found in the submitted image "
                                  "(disposition is coverage-gated upstream — a back-label "
                                  "warning may simply not be visible).")
        details[SubCheck.PREFIX_CAPS] = "No warning anchor located."
        details[SubCheck.WEIGHT_CONTRAST] = "No region to measure."
        return WarningResult(outcomes, details)

    if not region_quality_ok:
        outcomes[SubCheck.TEXT] = Outcome.UNVERIFIABLE
        details[SubCheck.TEXT] = ("Warning region image quality too low for a reliable "
                                  "comparison — check the label yourself or upload a clearer photo.")
    else:
        diff = word_diff(STATUTORY_WARNING, extracted_verbatim)
        exact = all(op == "equal" for op, _ in diff)
        if not exact:
            # OCR word segmentation is unreliable (dropped/inserted spaces yield
            # tokens like "BEVERAGESDURING"), and the located region can absorb a
            # neighboring line (e.g. a trailing "IMPORTED BY:"). The statute
            # prescribes the words: pass iff the full statutory statement appears
            # CONTIGUOUSLY in the whitespace-stripped character stream — any
            # wording change, omission, or interior insertion breaks containment.
            squash = lambda s: "".join(whitespace_only(s).casefold().split())
            exact = squash(STATUTORY_WARNING) in squash(extracted_verbatim)
        if not exact:
            # Comma↔period carve-out: at label point sizes a comma and a period
            # are near-identical glyphs, and OCR substitutes one for the other
            # (real case: 'GENERAL.' read where the label prints 'General,').
            # If folding commas to periods makes containment pass, the ONLY
            # deviation is that glyph — a probable OCR read error, not a proven
            # label defect. Screening principle: uncertainty → review, never a
            # confident wrong verdict. Substitution only: a MISSING comma
            # changes the char-stream length and still fails red.
            fold = lambda s: "".join(whitespace_only(s).casefold().split()).replace(",", ".")
            if fold(STATUTORY_WARNING) in fold(extracted_verbatim):
                confusable_punct = True
        if exact:
            outcomes[SubCheck.TEXT] = Outcome.PASS
            details[SubCheck.TEXT] = "The label's warning text matches the required text."
        elif confusable_punct:
            outcomes[SubCheck.TEXT] = Outcome.UNVERIFIABLE
            exp = next((t for op, t in diff if op == "expected"), "General,")
            fnd = next((t for op, t in diff if op == "found"), "GENERAL.")
            details[SubCheck.TEXT] = (
                f'The warning read "{fnd}" where the required text says "{exp}" — '
                "a comma/period difference at label size is usually an OCR read "
                "error, not a wording defect. Check the punctuation on the label "
                "yourself.")
        else:
            outcomes[SubCheck.TEXT] = Outcome.FAIL
            details[SubCheck.TEXT] = plain_sentence(diff)
        result_diff = diff
    caps = bool(PREFIX_CAPS_RE.search(extracted_verbatim))
    outcomes[SubCheck.PREFIX_CAPS] = Outcome.PASS if caps else Outcome.FAIL
    details[SubCheck.PREFIX_CAPS] = (
        '"GOVERNMENT WARNING:" appears in capital letters.' if caps
        else 'The heading must read "GOVERNMENT WARNING:" in all capital letters '
             '(§16.22(a)(2)) — the label prints it otherwise.')

    wc_map = {
        "ok": (Outcome.PASS, "Weight contrast between the heading and the statement body looks correct."),
        "no_contrast": (Outcome.FAIL, "No weight contrast between heading and body — either the heading "
                                       "is not bold or the body is bold; §16.22(a)(2) requires bold heading "
                                       "and non-bold body. Confirm which side visually."),
        "unknown": (Outcome.UNVERIFIABLE, "Bold weight could not be measured — confirm visually."),
    }
    o, msg = wc_map.get(weight_contrast, wc_map["unknown"])
    outcomes[SubCheck.WEIGHT_CONTRAST] = o
    details[SubCheck.WEIGHT_CONTRAST] = msg

    res = WarningResult(outcomes, details, confusable_punct=confusable_punct)
    # attach the diff on FAIL and on the confusable carve-out — the reviewer
    # confirming punctuation visually needs the diff boxes pointing at the glyph
    if outcomes.get(SubCheck.TEXT) == Outcome.FAIL or confusable_punct:
        res.diff_tokens = result_diff
    return res
