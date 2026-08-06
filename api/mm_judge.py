"""Deterministic judge for the multimodal second read (mm-ocr-augment
D-3, amendment 21). The model contributes eyes (a verbatim transcription);
THIS module contributes the verdict — pure functions, no model access,
so an adversarial transcription can only ever be compared, never obeyed.

Verdict semantics (asymmetric by design — the second reader is
statistically weaker than the primary OCR, so raw disagreement is noise):

- ``agrees``: the transcription supports the currently-expected reading.
  On a NEEDS_REVIEW row that means the application value was found (the
  most useful outcome on an unreadable crop). On a MISMATCH row it means
  the transcription confirms the MACHINE's differing read — the mismatch
  stands.
- ``sides_with_application``: MISMATCH row where the transcription
  contains the applicant's value instead — the one genuinely actionable
  disagreement (amber emphasis in the UI).
- ``differs``: matches neither expectation. Debug-block only, never a
  headline chip.

The warning adapter judges CONTENT WORDS ONLY — prefix typography and
weight contrast are stroke/case properties a transcription cannot attest
(eng finding F5); normalization strips case and punctuation, which also
absorbs the comma/period OCR-confusable class.
"""

from __future__ import annotations

import re

from .rules.abv import AbvVerdict, BevType, compare_abv, parse_abv
from .rules.warning import STATUTORY_WARNING

_NORM_RE = re.compile(r"[^A-Z0-9]+")

CONTENT_ONLY_NOTE = ("content words only — typography/weight not assessable "
                     "from a transcription")


def _norm(s: str | None) -> str:
    return _NORM_RE.sub(" ", (s or "").upper()).strip()


def _contains(expected: str | None, transcription: str) -> bool:
    e = _norm(expected)
    return bool(e) and e in _norm(transcription)


def _bev(application: dict) -> BevType:
    try:
        return BevType(application.get("beverage_type", "unspecified"))
    except ValueError:
        return BevType.UNSPECIFIED


def _verdict(found_app: bool, found_label: bool, status: str,
             note: str) -> tuple[str, str]:
    if found_app:
        if status == "MISMATCH":
            return "sides_with_application", (
                "transcription contains the application value — the second "
                "read sides with the applicant against the screening read; "
                + note)
        return "agrees", ("transcription contains the expected application "
                          "value; " + note)
    if found_label and status == "MISMATCH":
        return "agrees", ("transcription confirms the screening read — the "
                          "mismatch stands; " + note)
    return "differs", ("transcription matches neither the application value "
                       "nor the screening read; " + note)


def judge(field: str, status: str, transcription: str, application: dict,
          label_value: str | None = None) -> tuple[str, str]:
    """(verdict, note) for one field's transcription. Same derivations S2
    uses (BevType from the application, parse_abv on both sides); never
    raises — the caller wraps defensively anyway (amendment: judge
    exceptions become an ``error`` verdict, not a dead layer)."""
    if field == "alcohol_content":
        app_pct = parse_abv(application.get("alcohol_content") or "").percent
        reading = parse_abv(transcription)
        if reading.percent is None and reading.range_lo is None:
            return _verdict(False, _contains(label_value, transcription),
                            status, "no ABV statement found in transcription")
        v, note = compare_abv(app_pct, reading, _bev(application))
        # WITHIN_TOLERANCE is a legal match (amendment 21)
        found_app = v in (AbvVerdict.MATCH, AbvVerdict.WITHIN_TOLERANCE)
        return _verdict(found_app, _contains(label_value, transcription),
                        status, note)

    if field == "government_warning":
        found = _contains(STATUTORY_WARNING, transcription)
        return _verdict(found, _contains(label_value, transcription),
                        status, CONTENT_ONLY_NOTE)

    expected = application.get(field)
    return _verdict(_contains(expected, transcription),
                    _contains(label_value, transcription),
                    status, f"normalized containment vs application "
                            f"{field or 'value'}")
