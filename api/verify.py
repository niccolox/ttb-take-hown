"""Verification orchestrator: OCR words → locator → rules → pinned envelope.

Response contract (PLAN.md, Rev 2.1 amendments): schema_version "1",
request_id, screening_result, attention_state, timing_ms, fields[] each
{field, status, label_value, application_value, reason_code, evidence{bbox,
region_quality}, note, citation?}. Statuses: MATCH | LIKELY_MATCH |
WITHIN_TOLERANCE | MISMATCH | NEEDS_REVIEW | NOT_CHECKED | NOT_REQUIRED.
"""

from __future__ import annotations

import dataclasses

import time
import uuid
from dataclasses import asdict, dataclass

from .locator import Locator, Word
from .rules.abv import (AbvVerdict, BevType, abv_required, compare_abv,
                        parse_abv, proof_consistency, PCT_RE, PROOF_RE)
from .rules.net_contents import NET_RE, compare_net
from .rules.normalize import loose, whitespace_only
from .rules.warning import STATUTORY_WARNING, Outcome, SubCheck, validate_warning

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


_ALT_RANK = {"MATCH": 6, "LIKELY_MATCH": 5, "WITHIN_TOLERANCE": 4, "MISMATCH": 2,
             "NEEDS_REVIEW": 1, "NOT_CHECKED": 0}


def _text_field(name: str, expected: str | None, locator: Locator) -> FieldResult:
    """Registry class phrases use slash alternation ("sparkling wine/champagne"
    is class code 81 — either name satisfies it); no label prints the slash
    phrase verbatim. Try each alternative and keep the best result, reporting
    the full registry phrase as the application value."""
    if expected and "/" in expected:
        alts = [a.strip() for a in expected.split("/") if len(a.strip()) >= 3]
        if len(alts) >= 2:
            results = [_text_field_one(name, a, locator) for a in alts]
            best = max(results, key=lambda r: _ALT_RANK.get(r.status, 0))
            note = best.note
            if best.status in ("MATCH", "LIKELY_MATCH"):
                note = (f'Label matches "{best.application_value}" — one of the '
                        f'alternatives in the registry class phrase "{expected}".')
            return dataclasses.replace(best, application_value=expected, note=note)
    return _text_field_one(name, expected, locator)


def _text_field_one(name: str, expected: str | None, locator: Locator) -> FieldResult:
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
        # Absence without coverage proof is uncertainty, not a finding
        # (Rev 2.1: photos rarely establish that a region was adequately observed)
        return FieldResult(name, "NEEDS_REVIEW", None, expected, "not_found_in_image",
                           "Expected text was not found in the submitted image — "
                           "inspect the full label (it may be on another panel).", None)
    if loc.ambiguous:
        return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "ambiguous",
                           "Two similar regions match — check both candidates.",
                           _evidence(loc))
    if loc.min_conf < CONF_FLOOR:
        return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "unreadable",
                           "Found a likely region but it reads poorly — confirm from the crop.",
                           _evidence(loc))
    if loose(loc.text) == loose(expected):
        if whitespace_only(loc.text) == whitespace_only(expected):
            return FieldResult(name, "MATCH", loc.text, expected, None,
                               "Label matches the application exactly.", _evidence(loc))
        # Letter case is not a naming deviation: labels conventionally print in
        # capitals while applications use mixed case ("PASCAL DOQUET" = "Pascal
        # Doquet"). Only punctuation/spelling differences stay amber.
        if whitespace_only(loc.text).casefold() == whitespace_only(expected).casefold():
            return FieldResult(name, "MATCH", loc.text, expected, None,
                               "Label matches the application (letter case differs — "
                               "labels are conventionally printed in capitals).",
                               _evidence(loc))
        return FieldResult(name, "LIKELY_MATCH", loc.text, expected,
                           "case_punctuation_differs",
                           "Punctuation differs — compare both values.",
                           _evidence(loc))
    if loc.score >= 85:
        # High fuzzy but not normalized-equal is MISMATCH, never LIKELY (T1 rule) —
        # with a char-level carve-out (Rev 2.1 confusable doctrine): a single-glyph
        # difference (ZINPANDEL/Zinfandel) is within OCR error and goes to the human
        # with the crop; multi-character differences are genuine mismatches.
        from rapidfuzz.distance import Levenshtein
        dist = Levenshtein.distance(loose(loc.text), loose(expected))
        if dist <= max(1, len(loose(expected)) // 10):
            return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "possible_ocr_misread",
                               f'The label may read "{loc.text}" — within one character of the '
                               "application value, which is inside OCR error range. Check the crop.",
                               _evidence(loc))
        if loc.min_conf < 0.80:
            return FieldResult(name, "NEEDS_REVIEW", loc.text, expected, "unreadable",
                               "The label reads differently here but the image quality "
                               "is marginal — check the crop.", _evidence(loc))
        return FieldResult(name, "MISMATCH", loc.text, expected, "value_differs",
                           "Application and label differ.", _evidence(loc))
    return FieldResult(name, "MISMATCH", loc.text or None, expected, "value_differs",
                       "Application and label differ.", _evidence(loc))


def verify(words: list[Word], application: dict, image_gray=None) -> dict:
    t0 = time.perf_counter()
    try:
        bev = BevType(application.get("beverage_type", "unspecified"))
    except ValueError:                       # unknown type → strictest checks, never a 500
        bev = BevType.UNSPECIFIED
    locator = Locator(words)
    fields: list[FieldResult] = []

    if len(words) < TEXT_MASS_FLOOR:
        return _envelope("screening_incomplete", [FieldResult(
            "image", "NEEDS_REVIEW", None, None, "not_a_label",
            "This doesn't look like a label — very little text was found. "
            "Try a clearer photo of the label itself.")], t0)

    fields.append(_text_field("brand_name", application.get("brand_name"), locator))
    ct_result = _text_field("class_type", application.get("class_type"), locator)
    fields.append(ct_result)

    # optional registry-derived fields (COLA Detail): checked only when supplied.
    # grape_varietals uses the slash-alternation path — any listed varietal on
    # the label satisfies the check.
    for opt in ("fanciful_name", "origin", "vintage", "appellation", "grape_varietals"):
        val = (application.get(opt) or "").strip()
        if val:
            fields.append(_text_field(opt, val, locator))

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
    wc_outcome = "unknown"
    if warn_loc.found and image_gray is not None:
        regions = locator.warning_prefix_body()
        if regions:
            from .rules.contrast import weight_contrast
            wc_outcome, _wc_detail = weight_contrast(image_gray, *regions)
    diff_boxes = _warning_diff_boxes(locator) if warn_loc.found else []
    wr = validate_warning(warn_loc.text if warn_loc.found else None,
                          region_quality_ok=(warn_loc.min_conf >= CONF_FLOOR) if warn_loc.found else True,
                          weight_contrast=wc_outcome)
    sub = [{"check": c.value, "outcome": wr.outcomes[c].value, "detail": wr.details[c]}
           for c in SubCheck if c in wr.outcomes]
    text_o = wr.outcomes.get(SubCheck.TEXT)
    if text_o == Outcome.PASS and wr.outcomes[SubCheck.PREFIX_CAPS] == Outcome.PASS \
            and wc_outcome == "no_contrast":
        # §16.22(a)(2) violation the heuristic measured confidently: correct words,
        # correct caps, but no bold contrast — a red finding, not fine print
        w_status, w_code = "MISMATCH", "weight_contrast_violation"
    elif text_o == Outcome.PASS and wr.outcomes[SubCheck.PREFIX_CAPS] == Outcome.PASS:
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
                              _warn_evidence(warn_loc, diff_boxes, text_o),
                              wr.citation, sub))

    return _envelope(None, fields, t0)


def _warning_diff_boxes(locator: Locator) -> list[dict]:
    """Word boxes for the visual diff: where the located warning text deviates
    from the statutory text. 'differs' boxes sit on the deviating label words;
    'missing_here' marks the neighbors of an omission. Case-insensitive token
    compare (case is checked separately by prefix_caps)."""
    import difflib
    words = locator.warning_words()
    if not words:
        return []
    f = [w.text.casefold() for w in words]
    e = [t.casefold() for t in STATUTORY_WARNING.split()]
    boxes: list[dict] = []
    seen: set[tuple] = set()

    def add(word, kind):
        b = tuple(round(v, 1) for v in word.box)
        if b not in seen:
            seen.add(b)
            boxes.append({"box": list(b), "kind": kind})

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, e, f).get_opcodes():
        if op == "equal":
            continue
        if op == "insert" and i1 == len(e):
            continue                     # trailing neighbor text (e.g. "IMPORTED BY:")
                                         # — tolerated by the containment rule, not a diff
        if j2 > j1:                      # label words that differ / are extra
            for w in words[j1:j2]:
                add(w, "differs")
        else:                            # statutory words missing at this point
            for idx in (j1 - 1, j1):
                if 0 <= idx < len(words):
                    add(words[idx], "missing_here")
    return boxes


def _warn_evidence(warn_loc, diff_boxes: list[dict], text_outcome) -> dict | None:
    ev = _evidence(warn_loc) if warn_loc.found else None
    # attach only when the wording check didn't pass — a clean pass needs no diff
    if ev is not None and diff_boxes and text_outcome != Outcome.PASS:
        ev["diff_boxes"] = diff_boxes
    return ev


# MISMATCH outranks NOT_REQUIRED: a wrong value PRINTED on any panel is a real
# finding — legal absence elsewhere doesn't erase it. MATCH still beats MISMATCH
# (the field legally lives on any panel; found-correct wins).
_MERGE_RANK = {"MATCH": 6, "LIKELY_MATCH": 5, "WITHIN_TOLERANCE": 5,
               "MISMATCH": 3, "NOT_REQUIRED": 2, "NEEDS_REVIEW": 1, "NOT_CHECKED": 0}


def verify_multi(panels: list[tuple[list[Word], "object"]], application: dict) -> dict:
    """Multi-panel verification: run the single-image pipeline per panel and
    merge per field, preferring definitive positives — a field legally lives on
    ANY panel (the warning is usually on the back, §16.21), so a MATCH on one
    panel beats not-found on another; a genuine found-but-wrong (MISMATCH)
    outranks unreadable/absent. Evidence carries the panel index."""
    t0 = time.perf_counter()
    if not panels:
        return _envelope("screening_incomplete", [], t0)
    per_panel = []
    for idx, (words, gray) in enumerate(panels):
        r = verify(words, application, image_gray=gray)
        for f in r["fields"]:
            if f.get("evidence"):
                f["evidence"]["panel"] = idx
        per_panel.append(r)
    if len(per_panel) == 1:
        return per_panel[0]

    merged: dict[str, dict] = {}
    order: list[str] = []
    for r in per_panel:
        for f in r["fields"]:
            name = f["field"]
            if name not in merged:
                merged[name] = f
                order.append(name)
            elif _MERGE_RANK.get(f["status"], 0) > _MERGE_RANK.get(merged[name]["status"], 0):
                merged[name] = f
    fields = [merged[n] for n in order]
    out = _envelope_dicts(fields, t0)
    return out


def _envelope_dicts(fields: list[dict], t0: float) -> dict:
    statuses = [f["status"] for f in fields]
    if "MISMATCH" in statuses:
        screening = "mismatch_found"
    elif "NEEDS_REVIEW" in statuses:
        screening = "screening_incomplete"
    else:
        screening = "no_mismatch_found"
    attention = "action_required" if any(
        s in ("MISMATCH", "NEEDS_REVIEW", "WITHIN_TOLERANCE", "LIKELY_MATCH") for s in statuses) else "none"
    return {"schema_version": "1", "request_id": str(uuid.uuid4()),
            "screening_result": screening, "attention_state": attention,
            "timing_ms": {"total": round((time.perf_counter() - t0) * 1000)},
            "fields": fields}


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
