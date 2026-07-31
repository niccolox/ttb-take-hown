"""Verification orchestrator: OCR words → locator → rules → pinned envelope.

Response contract (PLAN.md, Rev 2.1 amendments): schema_version "1",
request_id, screening_result, attention_state, timing_ms, fields[] each
{field, status, label_value, application_value, reason_code, evidence{bbox,
region_quality}, note, citation?}. Statuses: MATCH | LIKELY_MATCH |
WITHIN_TOLERANCE | MISMATCH | NEEDS_REVIEW | NOT_CHECKED | NOT_REQUIRED.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass

from .locator import Locator, Word
from .rules.abv import (AbvVerdict, BevType, abv_required, compare_abv,
                        parse_abv, proof_consistency, PCT_RE, PROOF_RE)
from .rules.net_contents import NET_RE, compare_net
from .rules.normalize import loose
from .rules.warning import Outcome, SubCheck, validate_warning

CONF_FLOOR = 0.60          # word-confidence gate (tuned at M0)
TEXT_MASS_FLOOR = 4        # fewer located words → "doesn't look like a label"


@dataclass
class FieldResult:
    field: str
    status: str
    label_value: str | None
    application_value: str | None
    reason_code: str | None
    note: str
    evidence: dict | None = None
    citation: str | None = None
    sub_results: list[dict] | None = None


def _evidence(loc) -> dict | None:
    if loc and loc.box:
        return {"bbox": [round(v, 1) for v in loc.box],
                "region_quality": round(loc.min_conf, 3)}
    return None


def _text_field(name: str, expected: str | None, locator: Locator) -> FieldResult:
    if not expected:
        return FieldResult(name, "NOT_CHECKED", None, None, None,
                           "No application value entered.")
    loc = locator.find(expected)
    if not loc.found:
        if loc.score > 0 and loc.min_conf < CONF_FLOOR:
            return FieldResult(name, "NEEDS_REVIEW", loc.text or None, expected,
                               "unreadable",
                               "Couldn't read this part of the image — check the label "
                               "yourself or upload a clearer photo.", _evidence(loc))
        return FieldResult(name, "MISMATCH", None, expected, "not_found",
                           "Expected text was not found in the submitted image — "
                           "inspect the full label.", None)
    if loc.ambiguous:
        return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "ambiguous",
                           "Two similar regions match — check both candidates.",
                           _evidence(loc))
    if loc.min_conf < CONF_FLOOR:
        return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "unreadable",
                           "Found a likely region but it reads poorly — confirm from the crop.",
                           _evidence(loc))
    if loose(loc.text) == loose(expected):
        exact = loc.text.strip() == expected.strip()
        if exact:
            return FieldResult(name, "MATCH", loc.text, expected, None,
                               "Label matches the application exactly.", _evidence(loc))
        return FieldResult(name, "LIKELY_MATCH", loc.text, expected,
                           "case_punctuation_differs",
                           "Capitalization or punctuation differs — compare both values.",
                           _evidence(loc))
    if loc.score >= 85:
        # high fuzzy but not normalized-equal is MISMATCH, never LIKELY (T1 rule)
        return FieldResult(name, "MISMATCH", loc.text, expected, "value_differs",
                           "Application and label differ.", _evidence(loc))
    return FieldResult(name, "MISMATCH", loc.text or None, expected, "value_differs",
                       "Application and label differ.", _evidence(loc))


def verify(words: list[Word], application: dict) -> dict:
    t0 = time.perf_counter()
    bev = BevType(application.get("beverage_type", "unspecified"))
    locator = Locator(words)
    fields: list[FieldResult] = []

    if len(words) < TEXT_MASS_FLOOR:
        return _envelope("incomplete", [FieldResult(
            "image", "NEEDS_REVIEW", None, None, "not_a_label",
            "This doesn't look like a label — very little text was found. "
            "Try a clearer photo of the label itself.")], t0)

    fields.append(_text_field("brand_name", application.get("brand_name"), locator))
    ct_result = _text_field("class_type", application.get("class_type"), locator)
    fields.append(ct_result)

    # ABV — commodity-aware (Rev 2.1)
    app_abv_text = application.get("alcohol_content")
    abv_loc = locator.find_regex(PCT_RE)
    if not abv_loc.found:
        abv_loc = locator.find_regex(PROOF_RE)   # proof-only labels (converted 2:1)
    label_abv = parse_abv(abv_loc.text) if abv_loc.found else parse_abv("")
    if app_abv_text:
        app_abv = parse_abv(app_abv_text).percent
        if abv_loc.found:
            verdict, note = compare_abv(
                app_abv, label_abv, bev,
                digit_confidence_ok=abv_loc.min_conf >= CONF_FLOOR)
            citation = ("Magnitude per 27 CFR; drift permitted by Form 5100.31 "
                        "allowable-revision item 11") if verdict == AbvVerdict.WITHIN_TOLERANCE else None
            fields.append(FieldResult("alcohol_content", verdict.value, abv_loc.text,
                                      app_abv_text,
                                      "within_tolerance_confirm" if verdict == AbvVerdict.WITHIN_TOLERANCE else
                                      ("value_differs" if verdict == AbvVerdict.MISMATCH else None),
                                      note, _evidence(abv_loc), citation))
        else:
            required, why = abv_required(bev, ct_result.label_value or application.get("class_type"))
            if not required:
                fields.append(FieldResult("alcohol_content", "NOT_REQUIRED", None,
                                          app_abv_text, "not_required_for_commodity",
                                          f"No ABV found on the label — {why}", None,
                                          "27 CFR §4.36(a) / §7.63(a)(3)"))
            else:
                fields.append(FieldResult("alcohol_content", "NEEDS_REVIEW", None,
                                          app_abv_text, "not_found",
                                          f"ABV not found in the submitted image ({why}) — "
                                          "inspect the full label.", None))
    else:
        fields.append(FieldResult("alcohol_content", "NOT_CHECKED", abv_loc.text or None,
                                  None, None, "No application value entered."))

    # label-internal consistency (proof = 2×ABV)
    ok, note = proof_consistency(label_abv)
    if ok is not None:
        fields.append(FieldResult("internal_consistency",
                                  "MATCH" if ok else "MISMATCH",
                                  abv_loc.text, None, None if ok else "internal_inconsistency",
                                  note, _evidence(abv_loc), "27 CFR §5.65(b) (proof = 2×ABV)"))

    # net contents — molded-glass caveat is commodity-aware
    net_loc = locator.find_regex(NET_RE)
    verdict, note = compare_net(application.get("net_contents"),
                                net_loc.text if net_loc.found else None)
    if verdict == "NEEDS_REVIEW" and not net_loc.found and bev in (BevType.SPIRITS, BevType.MALT):
        note = ("Net contents not visible in the submitted image — it may be molded "
                "into the container (§5.70/§7.70). Check the bottle itself.")
        code = "not_visible_in_image"
    else:
        code = {"MISMATCH": "value_differs", "NEEDS_REVIEW": "unreadable"}.get(verdict)
    fields.append(FieldResult("net_contents", verdict,
                              net_loc.text if net_loc.found else None,
                              application.get("net_contents"), code, note,
                              _evidence(net_loc)))

    # government warning — always-on
    warn_loc = locator.find_warning()
    wr = validate_warning(warn_loc.text if warn_loc.found else None,
                          region_quality_ok=(warn_loc.min_conf >= CONF_FLOOR) if warn_loc.found else True)
    sub = [{"check": c.value, "outcome": wr.outcomes[c].value, "detail": wr.details[c]}
           for c in SubCheck if c in wr.outcomes]
    text_o = wr.outcomes.get(SubCheck.TEXT)
    if text_o == Outcome.PASS and wr.outcomes[SubCheck.PREFIX_CAPS] == Outcome.PASS:
        w_status, w_code = "MATCH", None
    elif text_o == Outcome.NOT_FOUND:
        w_status, w_code = "NEEDS_REVIEW", "not_visible_in_image"
    elif text_o == Outcome.UNVERIFIABLE:
        w_status, w_code = "NEEDS_REVIEW", "unreadable"
    else:
        w_status, w_code = "MISMATCH", "statutory_text_differs"
    fields.append(FieldResult("government_warning", w_status,
                              (warn_loc.text[:120] + "…") if warn_loc.found and len(warn_loc.text) > 120 else (warn_loc.text if warn_loc.found else None),
                              "27 CFR §16.21 statutory text (always checked)",
                              w_code,
                              wr.details.get(SubCheck.TEXT, ""),
                              _evidence(warn_loc) if warn_loc.found else None,
                              wr.citation, sub))

    return _envelope(None, fields, t0)


def _envelope(force_screening: str | None, fields: list[FieldResult], t0: float) -> dict:
    statuses = [f.status for f in fields]
    if force_screening:
        screening = force_screening
    elif "MISMATCH" in statuses:
        screening = "mismatch_found"
    elif "NEEDS_REVIEW" in statuses:
        screening = "screening_incomplete"
    else:
        screening = "no_mismatch_found"
    attention = "action_required" if any(
        s in ("MISMATCH", "NEEDS_REVIEW", "WITHIN_TOLERANCE", "LIKELY_MATCH") for s in statuses) else "none"
    return {
        "schema_version": "1",
        "request_id": str(uuid.uuid4()),
        "screening_result": screening,
        "attention_state": attention,
        "timing_ms": {"total": round((time.perf_counter() - t0) * 1000)},
        "fields": [asdict(f) for f in fields],
    }
