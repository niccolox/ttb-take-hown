"""Rules-engine unit tests — the plan's Section 6 boundary tables."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.rules.abv import (AbvVerdict, BevType, abv_required, compare_abv,
                           parse_abv, proof_consistency)
from api.rules.net_contents import compare_net, parse_net_ml
from api.rules.normalize import loose, whitespace_only
from api.rules.warning import (STATUTORY_WARNING, Outcome, SubCheck,
                               validate_warning)

# ── statutory constant checksum (guards editorial drift; Rev 2.1 provenance) ──

def test_statutory_checksum():
    h = hashlib.sha256(STATUTORY_WARNING.encode()).hexdigest()
    assert h == hashlib.sha256((
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth "
        "defects. (2) Consumption of alcoholic beverages impairs your ability to "
        "drive a car or operate machinery, and may cause health problems."
    ).encode()).hexdigest()


# ── warning: the planted traps ────────────────────────────────────────────────

def test_warning_exact_passes():
    r = validate_warning(STATUTORY_WARNING, weight_contrast="ok")
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS
    assert r.outcomes[SubCheck.PREFIX_CAPS] == Outcome.PASS
    assert r.outcomes[SubCheck.WEIGHT_CONTRAST] == Outcome.PASS

def test_titlecase_trap_fails_caps_only():
    text = STATUTORY_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    r = validate_warning(text)
    assert r.outcomes[SubCheck.PREFIX_CAPS] == Outcome.FAIL
    # wording is correct — the failure is (only) the caps requirement, so the
    # trap is reported by the sub-check that names the actual defect
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS


def test_all_caps_body_passes():
    """Common on real labels: entire warning printed in capitals. §16.21 fixes
    the words, not the body's case — 'ACCORDING' vs 'According' must PASS."""
    r = validate_warning(STATUTORY_WARNING.upper(), weight_contrast="ok")
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS
    assert r.outcomes[SubCheck.PREFIX_CAPS] == Outcome.PASS
    # and a real wording change in a caps body still fails
    bad = STATUTORY_WARNING.upper().replace("BIRTH DEFECTS", "BIRTH DEFECT")
    r2 = validate_warning(bad)
    assert r2.outcomes[SubCheck.TEXT] == Outcome.FAIL


def test_ocr_space_drop_passes():
    """OCR often glues adjacent words ('BEVERAGESDURING'). Spacing is not a
    §16.21 wording requirement — whitespace-stripped char stream must be equal,
    so a space drop passes but a real word change still fails."""
    glued = STATUTORY_WARNING.replace("beverages during", "beveragesduring")
    r = validate_warning(glued)
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS
    still_bad = STATUTORY_WARNING.replace("beverages during", "beverageduring")  # word changed too
    assert validate_warning(still_bad).outcomes[SubCheck.TEXT] == Outcome.FAIL


def test_trailing_neighbor_text_passes_interior_insert_fails():
    """The located region may absorb the next label line (real case: back strip
    ends '... HEALTH PROBLEMS. IMPORTED BY:'). Trailing neighbor copy is not a
    wording defect; text inserted INSIDE the statement still fails."""
    r = validate_warning(STATUTORY_WARNING.upper() + " IMPORTED BY: SOMEONE")
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS
    interior = STATUTORY_WARNING.replace("(2) Consumption",
                                         "ENJOY RESPONSIBLY (2) Consumption")
    assert validate_warning(interior).outcomes[SubCheck.TEXT] == Outcome.FAIL

def test_word_substitution_trap():
    text = STATUTORY_WARNING.replace("birth defects", "birth defect")
    r = validate_warning(text)
    assert r.outcomes[SubCheck.TEXT] == Outcome.FAIL
    assert '"defect' in r.details[SubCheck.TEXT]

def test_scrambled_words_fail():
    """The parth33320 token_set_ratio defect: scrambled words must NOT pass."""
    words = STATUTORY_WARNING.split()
    scrambled = " ".join([words[0], words[1]] + list(reversed(words[2:])))
    r = validate_warning(scrambled)
    assert r.outcomes[SubCheck.TEXT] == Outcome.FAIL

def test_low_quality_region_unverifiable_not_fail():
    r = validate_warning(STATUTORY_WARNING.replace("machinery", "rnachinery"),
                         region_quality_ok=False)
    assert r.outcomes[SubCheck.TEXT] == Outcome.UNVERIFIABLE  # never a false red

def test_missing_warning_not_found():
    r = validate_warning("KENTUCKY STRAIGHT BOURBON WHISKEY 750 ML")
    assert r.outcomes[SubCheck.TEXT] == Outcome.NOT_FOUND

def test_no_contrast_is_fail_side_indeterminate():
    r = validate_warning(STATUTORY_WARNING, weight_contrast="no_contrast")
    assert r.outcomes[SubCheck.WEIGHT_CONTRAST] == Outcome.FAIL
    assert "Confirm which side" in r.details[SubCheck.WEIGHT_CONTRAST]


# ── ABV: parser grammar + three-band model ───────────────────────────────────

def test_parse_formats():
    assert parse_abv("45% Alc./Vol. (90 Proof)").percent == 45.0
    assert parse_abv("45% Alc./Vol. (90 Proof)").proof == 90.0
    assert parse_abv("ALC. 45% BY VOL.").percent == 45.0
    assert parse_abv("5.2% ALC/VOL").percent == 5.2
    assert parse_abv("Alcohol 12.5 percent").percent == 12.5

def test_proof_only_converts():
    r = parse_abv("90 PROOF")
    assert r.percent == 45.0 and r.proof == 90.0

def test_range_label():
    r = parse_abv("Alcohol 11% to 13% by volume")
    assert (r.range_lo, r.range_hi) == (11.0, 13.0)
    v, _ = compare_abv(12.0, r, BevType.WINE)
    assert v == AbvVerdict.WITHIN_TOLERANCE          # inside range → amber, never green
    v, _ = compare_abv(14.5, r, BevType.WINE)
    assert v == AbvVerdict.MISMATCH

def test_exact_is_green():
    v, _ = compare_abv(45.0, parse_abv("45% ALC/VOL"), BevType.SPIRITS)
    assert v == AbvVerdict.MATCH

def test_within_band_is_amber_never_green():
    v, note = compare_abv(45.0, parse_abv("45.2% ALC/VOL"), BevType.SPIRITS)
    assert v == AbvVerdict.WITHIN_TOLERANCE and "confirm" in note

def test_outside_band_is_red():
    v, _ = compare_abv(45.0, parse_abv("46% ALC/VOL"), BevType.SPIRITS)
    assert v == AbvVerdict.MISMATCH

def test_band_edges():
    assert compare_abv(40.0, parse_abv("40.3%"), BevType.SPIRITS)[0] == AbvVerdict.WITHIN_TOLERANCE
    assert compare_abv(40.0, parse_abv("40.31%"), BevType.SPIRITS)[0] == AbvVerdict.MISMATCH

def test_wine_tiers_by_label_value():
    assert compare_abv(12.0, parse_abv("13.4%"), BevType.WINE)[0] == AbvVerdict.WITHIN_TOLERANCE   # ≤14 → ±1.5
    assert compare_abv(15.0, parse_abv("16.2%"), BevType.WINE)[0] == AbvVerdict.MISMATCH           # >14 → ±1.0... 1.2 out
    assert compare_abv(15.0, parse_abv("15.9%"), BevType.WINE)[0] == AbvVerdict.WITHIN_TOLERANCE

def test_class_boundary_never_rescued():
    # 13.8 vs 14.2 is within ±1.5 but crosses the 14% wine break → MISMATCH
    assert compare_abv(13.8, parse_abv("14.2%"), BevType.WINE)[0] == AbvVerdict.MISMATCH
    # malt: 0.4 vs 0.6 crosses the 0.5 floor
    assert compare_abv(0.4, parse_abv("0.6%"), BevType.MALT)[0] == AbvVerdict.MISMATCH
    # malt: 2.4 vs 2.6 crosses the 2.5 low-alcohol cap
    assert compare_abv(2.4, parse_abv("2.6%"), BevType.MALT)[0] == AbvVerdict.MISMATCH

def test_digit_confidence_gate():
    v, _ = compare_abv(45.0, parse_abv("45.2%"), BevType.SPIRITS, digit_confidence_ok=False)
    assert v == AbvVerdict.NEEDS_REVIEW              # shaky digits never earn amber

def test_proof_consistency():
    ok, _ = proof_consistency(parse_abv("45% Alc./Vol. (90 Proof)"))
    assert ok is True
    bad, note = proof_consistency(parse_abv("46% Alc./Vol. (90 Proof)"))
    assert bad is False and "INCONSISTENT" in note

def test_abv_requiredness_commodity_aware():
    req, _ = abv_required(BevType.SPIRITS, "Kentucky Straight Bourbon Whiskey")
    assert req is True
    req, note = abv_required(BevType.WINE, "California Chardonnay — Table Wine")
    assert req is False and "table" in note
    req, _ = abv_required(BevType.WINE, "Cabernet Sauvignon")
    assert req is True
    req, note = abv_required(BevType.MALT, "American Pale Ale")
    assert req is False and "confirm" in note


# ── net contents ─────────────────────────────────────────────────────────────

def test_net_units():
    assert parse_net_ml("750 mL") == 750.0
    assert parse_net_ml("0.75 L") == 750.0
    assert abs(parse_net_ml("25.4 FL OZ") - 751.2) < 0.5
    assert abs(parse_net_ml("1 PINT 0.9 FL. OZ.") - 499.8) < 0.5

def test_net_compare():
    assert compare_net("750 mL", "0.75 L")[0] == "MATCH"
    assert compare_net("750 mL", "700 mL")[0] == "MISMATCH"
    assert compare_net(None, "750 mL")[0] == "NOT_CHECKED"
    assert compare_net("750 mL", None)[0] == "NEEDS_REVIEW"


# ── normalization (Dave's case) ──────────────────────────────────────────────

def test_stones_throw():
    assert loose("STONE'S THROW") == loose("Stone's Throw")
    assert loose("STONE’S THROW") == loose("stone's throw")   # curly quote

def test_warning_normalization_preserves_case():
    assert whitespace_only("GOVERNMENT  WARNING:") == "GOVERNMENT WARNING:"
    assert whitespace_only("Government Warning:") != "GOVERNMENT WARNING:"


# ── real-photo dispositions (Napa corpus regressions) ────────────────────────

def _mk_locator(words_spec):
    from api.locator import Locator, Word
    return Locator([Word(t, (x, y, x + len(t) * 10, y + 20), c) for t, x, y, c in words_spec])


def test_not_found_is_review_not_mismatch():
    from api.verify import _text_field
    loc = _mk_locator([("MERLOT", 10, 10, 0.95), ("NAPA", 10, 40, 0.95)])
    r = _text_field("brand_name", "Silver Oak", loc)
    assert r.status == "NEEDS_REVIEW" and r.reason_code == "not_found_in_image"


def test_single_glyph_confusable_is_review():
    from api.verify import _text_field
    loc = _mk_locator([("ZINPANDEL", 10, 10, 0.95)])
    r = _text_field("class_type", "Zinfandel", loc)
    assert r.status == "NEEDS_REVIEW" and r.reason_code == "possible_ocr_misread"


def test_all_caps_brand_matches_capitalized_application():
    """Label 'PASCAL DOQUET' vs application 'Pascal Doquet' is a green MATCH —
    case is presentation, not naming. Punctuation differences stay amber."""
    from api.verify import _text_field
    loc = _mk_locator([("PASCAL", 10, 10, 0.95), ("DOQUET", 100, 10, 0.95)])
    r = _text_field("brand_name", "Pascal Doquet", loc)
    assert r.status == "MATCH"
    loc2 = _mk_locator([("STONE\u2019S", 10, 10, 0.95), ("THROW", 100, 10, 0.95)])
    r2 = _text_field("brand_name", "Stone's Throw", loc2)   # curly vs straight quote
    assert r2.status == "LIKELY_MATCH"
    # a genuinely dropped apostrophe stays in review (possible OCR misread)
    loc3 = _mk_locator([("STONES", 10, 10, 0.95), ("THROW", 100, 10, 0.95)])
    assert _text_field("brand_name", "Stone's Throw", loc3).status == "NEEDS_REVIEW"


def test_optional_registry_fields_verified_when_supplied():
    """COLA Detail extras (fanciful name, origin, vintage, appellation,
    varietals) become checked fields only when the application carries them."""
    from api.locator import Word
    from api.verify import verify
    mk = lambda t, y: [Word(w, (10 + i * 110, y, 100 + i * 110, y + 20), 0.95)
                       for i, w in enumerate(t.split())]
    words = (mk("CHATEAU LE COTEAU", 10) + mk("PELOPEE", 40)
             + mk("MARGAUX 2022", 70) + mk("PRODUCT OF FRANCE", 100)
             + mk("TABLE RED WINE", 130))
    app = {"beverage_type": "wine", "brand_name": "Chateau Le Coteau",
           "class_type": "table red wine", "fanciful_name": "Pelopee",
           "origin": "france", "vintage": "2022", "appellation": "Margaux"}
    result = verify(words, app)
    by = {f["field"]: f["status"] for f in result["fields"]}
    for name in ("brand_name", "class_type", "fanciful_name", "origin",
                 "vintage", "appellation"):
        assert by[name] in ("MATCH", "LIKELY_MATCH"), (name, by[name])
    # absent from application → not in the result at all
    assert "grape_varietals" not in by


def test_class_slash_phrase_matches_either_alternative():
    """Registry class 'sparkling wine/champagne' is an alternation — a label
    printing CHAMPAGNE satisfies it (and the note says which side matched)."""
    from api.verify import _text_field
    loc = _mk_locator([("CHAMPAGNE", 10, 10, 0.95), ("BRUT", 130, 10, 0.95)])
    r = _text_field("class_type", "sparkling wine/champagne", loc)
    assert r.status == "MATCH"
    assert r.application_value == "sparkling wine/champagne"
    assert "champagne" in r.note
    loc2 = _mk_locator([("SPARKLING", 10, 10, 0.95), ("WINE", 120, 10, 0.95)])
    assert _text_field("class_type", "sparkling wine/champagne", loc2).status == "MATCH"
    loc3 = _mk_locator([("MERLOT", 10, 10, 0.95)])
    r3 = _text_field("class_type", "sparkling wine/champagne", loc3)
    assert r3.status == "NEEDS_REVIEW"      # neither alternative found → honest review


def test_similar_but_different_brand_never_passes():
    # T1 safety property: 'OLD TOM DISTILLING CO' must never MATCH/LIKELY-MATCH
    # 'OLD TOM DISTILLERY'. Below the locator threshold it surfaces as
    # review-not-found (coverage-honest); at/above threshold it's MISMATCH.
    from api.verify import _text_field
    loc = _mk_locator([("OLD", 10, 10, 0.95), ("TOM", 50, 10, 0.95),
                       ("DISTILLING", 90, 10, 0.95), ("CO", 200, 10, 0.95)])
    r = _text_field("brand_name", "OLD TOM DISTILLERY", loc)
    assert r.status in ("MISMATCH", "NEEDS_REVIEW")
    assert r.status not in ("MATCH", "LIKELY_MATCH")


# ── COLA Cloud pipeline (pure manifest builder) ──────────────────────────────

def test_colacloud_entry_builder():
    from api.eval.colacloud_pipeline import build_entry, net_contents_str, pick_image
    detail = {"ttb_id": "23001001000123", "brand_name": "OLD TOM DISTILLERY",
              "class_name": "STRAIGHT BOURBON WHISKY", "abv": 45.0,
              "volume": 750, "volume_unit": "milliliters",
              "approval_date": "2023-05-01", "permit_number": "KY-DSP-1",
              "product_name": "Old Tom Small Batch", "origin_name": "american",
              "images": [{"image_url": "https://x/f.jpg", "container_position": "front"},
                         {"image_url": "https://x/b.jpg", "container_position": "back"}]}
    e = build_entry(detail, "distilled_spirits", "23001001000123.jpg")
    assert e["application"]["alcohol_content"] == "45.0%"
    assert e["application"]["net_contents"] == "750 mL"
    assert e["application"]["beverage_type"] == "distilled_spirits"
    assert e["provenance"]["ttb_id"] == "23001001000123"
    url, pos = pick_image(detail)
    assert url.endswith("f.jpg") and pos == "front"
    reg = e["registry"]
    assert "serial_number" not in reg   # applicant serial is NOT derivable from the TTB ID
    assert reg["class_type_code"] == "STRAIGHT BOURBON WHISKY"
    assert reg["fanciful_name"] == "Old Tom Small Batch"
    assert reg["permit_number"] == "KY-DSP-1"
    assert "grape_varietals" not in reg              # empty fields omitted
    assert net_contents_str(0.75, "liters") == "0.75 L"
    assert net_contents_str(None, None) == ""


def test_colacloud_pick_panels_front_and_back():
    from api.eval.colacloud_pipeline import pick_panels
    detail = {"images": [{"image_url": "https://x/b.jpg", "container_position": "back"},
                         {"image_url": "https://x/f.jpg", "container_position": "front"}]}
    panels = pick_panels(detail)
    assert panels == [("https://x/f.jpg", "front"), ("https://x/b.jpg", "back")]
    # front-only COLA: one panel, no invented back
    assert pick_panels({"images": [{"image_url": "https://x/f.jpg",
                                    "container_position": "front"}]}) == [("https://x/f.jpg", "front")]
    # no positions at all → falls back to pick_image
    assert pick_panels({"main_image_url": "https://x/m.jpg"}) == [("https://x/m.jpg", "main")]


# ── multi-panel verification (front + back label) ────────────────────────────

def test_verify_multi_merges_warning_from_back_panel():
    """§16.21 warning lives on the BACK label: found there → field passes, and
    evidence records which panel it came from."""
    from api.locator import Word
    from api.verify import verify_multi

    def words_of(texts, y0=10):
        out, y = [], y0
        for t in texts:
            x = 10
            for w in t.split():
                out.append(Word(w, (x, y, x + len(w) * 12, y + 20), 0.96))
                x += len(w) * 12 + 8
            y += 28
        return out

    front = words_of(["OLD TOM DISTILLERY", "KENTUCKY STRAIGHT BOURBON WHISKEY",
                      "45% ALC/VOL", "750 ML"])
    from api.rules.warning import STATUTORY_WARNING
    wtxt = STATUTORY_WARNING.split()
    back = words_of([" ".join(wtxt[i:i + 8]) for i in range(0, len(wtxt), 8)])

    app = {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM DISTILLERY",
           "class_type": "Kentucky Straight Bourbon Whiskey",
           "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}

    single = verify_multi([(front, None)], app)
    warn_single = next(f for f in single["fields"] if f["field"] == "government_warning")
    assert warn_single["status"] in ("NEEDS_REVIEW", "MISMATCH")   # absent on front

    merged = verify_multi([(front, None), (back, None)], app)
    by = {f["field"]: f for f in merged["fields"]}
    assert by["government_warning"]["status"] in ("MATCH", "LIKELY_MATCH", "NEEDS_REVIEW")
    # brand found on front stays authoritative; its evidence names panel 0
    assert by["brand_name"]["status"] in ("MATCH", "LIKELY_MATCH")
    if by["brand_name"].get("evidence"):
        assert by["brand_name"]["evidence"]["panel"] == 0
    # warning evidence, when present, points at the back panel
    if by["government_warning"].get("evidence"):
        assert by["government_warning"]["evidence"]["panel"] == 1


def test_verify_multi_match_beats_not_found():
    from api.locator import Word
    from api.verify import verify_multi
    mk = lambda t, y: [Word(w, (10 + i * 90, y, 90 + i * 90, y + 20), 0.95)
                       for i, w in enumerate(t.split())]
    front = mk("SILVER OAK", 10) + mk("CABERNET SAUVIGNON", 40)
    back = mk("PRODUCED AND BOTTLED BY", 10)
    app = {"beverage_type": "wine", "brand_name": "SILVER OAK",
           "class_type": "Cabernet Sauvignon"}
    merged = verify_multi([(front, None), (back, None)], app)
    by = {f["field"]: f for f in merged["fields"]}
    assert by["brand_name"]["status"] == "MATCH"      # back's not-found never demotes


def test_recover_orphans_panel_suffix_grouping(tmp_path, monkeypatch):
    """Panel files ({ttb_id}_back.jpg) must never be looked up as TTB IDs
    (the 404 '26203001000245_back not found' bug), and panels of one COLA
    recover into ONE entry."""
    import api.eval.colacloud_pipeline as cp
    d = tmp_path / "wine"; d.mkdir()
    # entry already in manifest, with panel files referenced
    (d / "111_front.jpg").write_bytes(b"x"); (d / "111_back.jpg").write_bytes(b"x")
    # true orphan with two panels
    (d / "222_front.jpg").write_bytes(b"x"); (d / "222_back.jpg").write_bytes(b"x")
    manifest = [{"id": "111", "file": "111_front.jpg",
                 "files": [{"file": "111_front.jpg", "panel": "front"},
                           {"file": "111_back.jpg", "panel": "back"}],
                 "application": {}, "provenance": {}}]
    (d / "manifest.json").write_text(__import__("json").dumps(manifest))
    monkeypatch.setattr(cp, "OUT_BASE", tmp_path)

    looked_up = []
    class FakeColas:
        def get(self, tid):
            looked_up.append(tid)
            return {"ttb_id": tid, "brand_name": "B", "class_name": "C",
                    "abv": 12.0, "volume": 750, "volume_unit": "milliliters"}
    class FakeClient:
        colas = FakeColas()
        def close(self): pass
    monkeypatch.setattr(cp, "setup_logging", lambda: None)
    import colacloud
    monkeypatch.setattr(colacloud, "ColaCloud", lambda api_key: FakeClient())
    monkeypatch.setattr(cp.time, "sleep", lambda s: None)

    n = cp.recover_orphans("wine", api_key="k")
    assert looked_up == ["222"]          # never '222_back', never '111*'
    out = __import__("json").loads((d / "manifest.json").read_text())
    assert len(out) == 2 and n == 2
    e = [m for m in out if m["id"] == "222"][0]
    assert e["file"] == "222_front.jpg"
    assert [f["panel"] for f in e["files"]] == ["front", "back"]


# ── warning visual diff (word-level discrepancy boxes) ───────────────────────

def test_warning_diff_boxes_mark_deviating_words():
    """The visual diff boxes the exact label words that deviate from §16.21 —
    pinned to the real comma/period OCR case ('GENERAL.' for 'General,')."""
    from api.locator import Locator, Word
    from api.verify import _warning_diff_boxes
    from api.rules.warning import STATUTORY_WARNING

    bad = STATUTORY_WARNING.replace("General,", "GENERAL.").upper()
    words, x, y = [], 10, 10
    for tok in bad.split():
        if x > 900:
            x, y = 10, y + 28
        words.append(Word(tok, (x, y, x + len(tok) * 9, y + 20), 0.95))
        x += len(tok) * 9 + 8
    loc = Locator(words)
    assert loc.find_warning().found
    boxes = _warning_diff_boxes(loc)
    assert boxes, "a deviation must produce diff boxes"
    flagged = [b for b in boxes if b["kind"] == "differs"]
    assert len(flagged) == 1                     # only the deviating word is boxed
    gw = next(w for w in loc.warning_words() if w.text == "GENERAL.")
    assert flagged[0]["box"] == [round(v, 1) for v in gw.box]

    # an omission marks its neighbors with 'missing_here'
    missing = STATUTORY_WARNING.upper().replace("BIRTH DEFECTS. ", "")
    words2 = [Word(tok, (10 + i * 60, 10 + (i // 12) * 28, 60 + i * 60, 30 + (i // 12) * 28), 0.95)
              for i, tok in enumerate(missing.split())]
    loc2 = Locator(words2)
    assert loc2.find_warning().found
    kinds = {b["kind"] for b in _warning_diff_boxes(loc2)}
    assert "missing_here" in kinds


def test_warning_diff_boxes_ignore_trailing_neighbor_text():
    """Absorbed trailing label copy (tolerated by containment) is not boxed —
    only genuine deviations inside the statement are."""
    from api.locator import Locator, Word
    from api.verify import _warning_diff_boxes
    from api.rules.warning import STATUTORY_WARNING
    txt = STATUTORY_WARNING.replace("General,", "GENERAL.").upper() + " IMPORTED BY SOMEONE"
    words = [Word(tok, (10 + (i % 12) * 70, 10 + (i // 12) * 28,
                        70 + (i % 12) * 70, 30 + (i // 12) * 28), 0.95)
             for i, tok in enumerate(txt.split())]
    loc = Locator(words)
    assert loc.find_warning().found
    boxes = _warning_diff_boxes(loc)
    flagged_words = {tuple(b["box"]) for b in boxes}
    by_box = {tuple(round(v, 1) for v in w.box): w.text for w in loc.warning_words()}
    texts = {by_box[b] for b in flagged_words}
    assert "GENERAL." in texts
    assert not {"IMPORTED", "BY", "SOMEONE"} & texts


def test_warning_diff_boxes_empty_on_exact_text():
    from api.locator import Locator, Word
    from api.verify import _warning_diff_boxes
    from api.rules.warning import STATUTORY_WARNING
    words = [Word(tok, (10 + (i % 12) * 70, 10 + (i // 12) * 28,
                        70 + (i % 12) * 70, 30 + (i // 12) * 28), 0.95)
             for i, tok in enumerate(STATUTORY_WARNING.split())]
    loc = Locator(words)
    assert loc.find_warning().found
    assert _warning_diff_boxes(loc) == []


# ── DuckDB session store ─────────────────────────────────────────────────────

def test_session_store_roundtrip(tmp_path, monkeypatch):
    from api import session_store as ss
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "state.duckdb")
    assert ss.load_session() is None and ss.session_summary() is None

    items = [{"file_name": "a_front.jpg", "state": "done", "override": "approve",
              "application": {"brand_name": "OLD TOM"},
              "result": {"screening_result": "no_mismatch_found", "fields": []}},
             {"file_name": "b.jpg", "state": "waiting", "override": None,
              "application": {"brand_name": "B"}, "result": None}]
    blobs = [(0, "front", "a_front.jpg", "image/jpeg", b"\xff\xd8front"),
             (0, "back", "a_back.jpg", "image/jpeg", b"\xff\xd8back"),
             (1, "front", "b.jpg", "image/png", b"\x89PNGb")]
    info = ss.save_session(items, blobs)
    assert info["item_count"] == 2

    s = ss.load_session()
    assert s["items"][0]["override"] == "approve"
    assert s["items"][0]["result"]["screening_result"] == "no_mismatch_found"
    assert [p["panel"] for p in s["items"][0]["panels"]] == ["front", "back"]
    assert s["items"][1]["result"] is None
    data, mime = ss.get_panel(0, "back")
    assert data == b"\xff\xd8back" and mime == "image/jpeg"
    assert ss.get_panel(9, "front") is None

    # save replaces (single-slot semantics), clear empties
    ss.save_session(items[:1], blobs[:2])
    assert ss.session_summary()["item_count"] == 1
    ss.clear_session()
    assert ss.load_session() is None
