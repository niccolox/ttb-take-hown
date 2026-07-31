"""Single source of truth for text normalization (PLAN.md 0E: one shared module —
prevents the drift where the warning comparator and brand comparator normalize
differently)."""

from __future__ import annotations

import re
import unicodedata

_QUOTES = {"’": "'", "‘": "'", "“": '"', "”": '"', "′": "'"}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def unify_quotes(s: str) -> str:
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    return s


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def whitespace_only(s: str) -> str:
    """The ONLY normalization allowed for the statutory warning text (case and
    punctuation preserved — §16.21 comparison is exact)."""
    return collapse_ws(nfc(s))


def loose(s: str) -> str:
    """Brand/class-type normalization: NFC, quote unification, whitespace collapse,
    casefold. Used for LIKELY MATCH determination — never for the warning."""
    return collapse_ws(unify_quotes(nfc(s))).casefold()
