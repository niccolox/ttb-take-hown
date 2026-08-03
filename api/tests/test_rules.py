"""Rules-engine unit tests — the plan's Section 6 boundary tables."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.rules.abv import (AbvVerdict, BevType, abv_format_legality,
                           abv_required, compare_abv, parse_abv,
                           proof_consistency)
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

def test_comma_period_confusable_needs_review_not_red():
    """Real case: OCR reads 'GENERAL.' where the label prints 'General,'.
    Comma vs period at label point size is a probable OCR glyph error — carve
    out to UNVERIFIABLE (→ NEEDS_REVIEW), never a confident red MISMATCH."""
    bad = STATUTORY_WARNING.upper().replace("GENERAL,", "GENERAL.")
    r = validate_warning(bad)
    assert r.outcomes[SubCheck.TEXT] == Outcome.UNVERIFIABLE
    assert r.confusable_punct
    assert "comma/period" in r.details[SubCheck.TEXT]
    assert r.diff_tokens  # the reviewer still gets diff boxes to confirm against

def test_period_read_as_comma_also_carved_out():
    r = validate_warning(STATUTORY_WARNING.replace("defects. (2)", "defects, (2)"))
    assert r.outcomes[SubCheck.TEXT] == Outcome.UNVERIFIABLE
    assert r.confusable_punct

def test_confusable_plus_real_word_change_still_fails():
    bad = (STATUTORY_WARNING.upper()
           .replace("GENERAL,", "GENERAL.")
           .replace("BIRTH DEFECTS", "BIRTH DEFECT"))
    r = validate_warning(bad)
    assert r.outcomes[SubCheck.TEXT] == Outcome.FAIL
    assert not r.confusable_punct

def test_dropped_comma_still_fails():
    """Substitution only: a MISSING comma shortens the char stream — the fold
    can't rescue it, and a dropped glyph stays a red wording finding."""
    r = validate_warning(STATUTORY_WARNING.replace("General,", "General"))
    assert r.outcomes[SubCheck.TEXT] == Outcome.FAIL
    assert not r.confusable_punct

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


# ── §4.36 audit backfill (TTB wine-ABV guidance page, TTB G 2019-2) ──────────

def test_hyphen_range_parses_like_ttb_examples():
    """TTB's own §4.36 examples are hyphenated ('17%-19% ALC. BY VOL.') —
    TO-only parsing read them as a specific 17%."""
    r = parse_abv("17%-19% ALC. BY VOL.")
    assert (r.range_lo, r.range_hi) == (17.0, 19.0)
    r2 = parse_abv("9%–12% alc. by vol.")                       # en dash
    assert (r2.range_lo, r2.range_hi) == (9.0, 12.0)
    v, _ = compare_abv(18.0, r, BevType.WINE)
    assert v == AbvVerdict.WITHIN_TOLERANCE


def test_wine_range_span_caps():
    # ≤14%: span may not exceed 3 points — 9–13 is 4 points, illegal
    v, note = compare_abv(11.0, parse_abv("9% to 13% alc by vol"), BevType.WINE)
    assert v == AbvVerdict.MISMATCH and "may not exceed" in note
    # >14%: 2-point span is the page's own legal example
    v2, _ = compare_abv(18.0, parse_abv("17%-19% ALC. BY VOL."), BevType.WINE)
    assert v2 == AbvVerdict.WITHIN_TOLERANCE
    # >14%: 3-point span exceeds the 2-point cap
    v3, _ = compare_abv(18.0, parse_abv("16%-19% ALC BY VOL"), BevType.WINE)
    assert v3 == AbvVerdict.MISMATCH


def test_wine_range_may_not_cross_class_limit():
    v, note = compare_abv(14.0, parse_abv("13% to 15% alcohol by volume"), BevType.WINE)
    assert v == AbvVerdict.MISMATCH and "class" in note


def test_wine_upper_tax_breaks_and_exact_14_band():
    # the 21% and 24% taxable-grade breaks are as un-rescuable as 14%
    assert compare_abv(20.5, parse_abv("21.5%"), BevType.WINE)[0] == AbvVerdict.MISMATCH
    assert compare_abv(23.5, parse_abv("24.2%"), BevType.WINE)[0] == AbvVerdict.MISMATCH
    # a label stating exactly 14.0% sits in the '14% or less' tier → ±1.5
    assert compare_abv(12.6, parse_abv("14%"), BevType.WINE)[0] == AbvVerdict.WITHIN_TOLERANCE


def test_abv_format_legality_wine_only():
    from api.rules.abv import abv_format_legality
    assert abv_format_legality("12.5% ABV", BevType.WINE)[0] == "FAIL"
    assert abv_format_legality("A.B.V. 12.5%", BevType.WINE)[0] == "FAIL"
    assert abv_format_legality("ALC. 12.5% BY VOL.", BevType.WINE)[0] == "PASS"
    assert abv_format_legality("Alcohol 12.5% by volume", BevType.WINE)[0] == "PASS"
    assert abv_format_legality("12.5% ABV", BevType.SPIRITS) is None   # wine-only assertion
    assert abv_format_legality(None, BevType.WINE) is None


def _label_words(lines, start_y=10):
    from api.locator import Word
    out, y = [], start_y
    for text in lines:
        x = 10
        for w in text.split():
            out.append(Word(w, (x, y, x + len(w) * 12, y + 20), 0.96))
            x += len(w) * 12 + 8
        y += 28
    return out


def test_table_designation_does_not_excuse_missing_abv_over_14():
    """A declared 16% wine with a 'Table Wine' class and no printed ABV must
    NOT get NOT_REQUIRED — above 14% the statement is mandatory and the
    designation itself is suspect (§4.36(a))."""
    from api.verify import verify
    words = _label_words(["SEABREEZE CELLARS", "Red Table Wine", "750 mL"])
    app = {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
           "class_type": "Red Table Wine", "alcohol_content": "16%",
           "net_contents": "750 mL"}
    f = next(x for x in verify(words, app)["fields"] if x["field"] == "alcohol_content")
    assert f["status"] == "NEEDS_REVIEW"
    assert f["reason_code"] == "designation_band_conflict"


def test_abv_format_defect_escalates_match_to_amber():
    """Label prints '12.5% ABV' — the value matches the application but the
    wording is prohibited on wine labels: green becomes amber with a format
    sub-result, never red."""
    from api.verify import verify
    words = _label_words(["SEABREEZE CELLARS", "California Chardonnay — Table Wine",
                          "12.5% ABV", "750 mL"])
    app = {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
           "class_type": "California Chardonnay — Table Wine",
           "alcohol_content": "12.5%", "net_contents": "750 mL"}
    f = next(x for x in verify(words, app)["fields"] if x["field"] == "alcohol_content")
    assert f["status"] == "NEEDS_REVIEW"
    assert f["reason_code"] == "format_nonstandard"
    assert f["sub_results"] and f["sub_results"][0]["outcome"] == "FAIL"
    # and the same wording on a spirits label stays out of scope (no sub-check)
    app_sp = {"beverage_type": "distilled_spirits", "brand_name": "SEABREEZE CELLARS",
              "class_type": "California Chardonnay — Table Wine",
              "alcohol_content": "12.5%", "net_contents": "750 mL"}
    f2 = next(x for x in verify(words, app_sp)["fields"] if x["field"] == "alcohol_content")
    assert f2["sub_results"] is None


# ── part 4 wine audit (docs/research/wine-labeling-audit-ttb.md, W-1..W-6) ───

_WINE_APP_FULL = {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
                  "class_type": "California Chardonnay — Table Wine",
                  "alcohol_content": "12.5%", "net_contents": "750 mL"}
_WINE_LINES_FULL = ["SEABREEZE CELLARS", "California Chardonnay — Table Wine",
                    "12.5% alc. by vol.", "750 mL", "Contains Sulfites",
                    "Vinted and bottled by Seabreeze Cellars, Napa, California"]


def _wine_fields(lines, app):
    from api.verify import verify
    return {f["field"]: f for f in verify(_label_words(lines), app)["fields"]}


def test_wine_fill_standards():
    from api.rules.wine import wine_fill_authorized
    assert wine_fill_authorized(750.0)[0] is True
    assert wine_fill_authorized(355.0)[0] is True
    assert wine_fill_authorized(723.0)[0] is False
    assert wine_fill_authorized(5000.0)[0] is True           # 4–17 L in even liters
    assert wine_fill_authorized(4500.0)[0] is False          # 4–17 L, not even liters
    assert wine_fill_authorized(18000.0)[0] is True          # ≥18 L exempt


def test_wine_nonstandard_fill_escalates_matching_values():
    """Label and application AGREE on 723 mL — agreement is not authorization:
    723 mL is not a §4.72 standard of fill → amber, never green. Spirits have
    no such list — same values stay green."""
    fs = _wine_fields([*_WINE_LINES_FULL[:3], "723 mL", *_WINE_LINES_FULL[4:]],
                      {**_WINE_APP_FULL, "net_contents": "723 mL"})
    assert fs["net_contents"]["status"] == "NEEDS_REVIEW"
    assert fs["net_contents"]["reason_code"] == "nonstandard_fill"
    fs2 = _wine_fields(["OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
                        "45% Alc./Vol.", "723 mL"],
                       {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM DISTILLERY",
                        "class_type": "Kentucky Straight Bourbon Whiskey",
                        "alcohol_content": "45%", "net_contents": "723 mL"})
    assert fs2["net_contents"]["status"] == "MATCH"


def test_sulfite_and_name_address_presence():
    fs = _wine_fields(_WINE_LINES_FULL, _WINE_APP_FULL)
    assert fs["sulfite_declaration"]["status"] == "MATCH"
    assert fs["name_address"]["status"] == "MATCH"
    bare = _wine_fields(_WINE_LINES_FULL[:4], _WINE_APP_FULL)   # no sulfite/bottler lines
    assert bare["sulfite_declaration"]["status"] == "NEEDS_REVIEW"
    assert bare["sulfite_declaration"]["reason_code"] == "sulfite_declaration_not_found"
    assert bare["name_address"]["status"] == "NEEDS_REVIEW"
    # wine-only fields: spirits verifies without them
    sp = _wine_fields(["OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
                       "45% Alc./Vol.", "750 mL"],
                      {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM DISTILLERY",
                       "class_type": "Kentucky Straight Bourbon Whiskey",
                       "alcohol_content": "45%", "net_contents": "750 mL"})
    assert "sulfite_declaration" not in sp and "name_address" not in sp


def test_sulphites_spelling_accepted():
    fs = _wine_fields([*_WINE_LINES_FULL[:4], "Contains Sulphites",
                       _WINE_LINES_FULL[5]], _WINE_APP_FULL)
    assert fs["sulfite_declaration"]["status"] == "MATCH"


def test_appellation_required_with_vintage_or_varietal():
    fs = _wine_fields(_WINE_LINES_FULL, {**_WINE_APP_FULL, "vintage": "2023"})
    assert fs["appellation"]["status"] == "NEEDS_REVIEW"
    assert fs["appellation"]["reason_code"] == "appellation_required"
    # supplying the appellation satisfies the condition (normal text-match row)
    fs2 = _wine_fields([*_WINE_LINES_FULL, "2023 Napa Valley"],
                       {**_WINE_APP_FULL, "vintage": "2023", "appellation": "Napa Valley"})
    assert fs2["appellation"]["reason_code"] != "appellation_required"


def test_wine_under_7_percent_notes_fda():
    fs = _wine_fields([*_WINE_LINES_FULL[:2], "6% alc. by vol.", *_WINE_LINES_FULL[3:]],
                      {**_WINE_APP_FULL, "alcohol_content": "6%"})
    assert "FDA" in fs["alcohol_content"]["note"]


def test_wine_net_molded_carveout():
    """Wine may blow/brand net contents into the glass (§4.37) — the
    not-visible note used to fire only for spirits/malt."""
    fs = _wine_fields([l for l in _WINE_LINES_FULL if l != "750 mL"], _WINE_APP_FULL)
    assert fs["net_contents"]["status"] == "NEEDS_REVIEW"
    assert fs["net_contents"]["reason_code"] == "not_visible_in_image"
    assert "molded" in fs["net_contents"]["note"]


# ── Wine BAM chapter 10 sample labels (source/c10-sample-wine-labels.pdf) ────
# TTB's own approvable formats as fixtures: every one must screen clean.

_BAM_WARN = ["GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD",
             "NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH",
             "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE",
             "A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."]


def test_bam_varietal_percentages_do_not_hijack_abv():
    """BAM p.10-7 (three-piece blend): '60% CHARDONNAY' sits above the real
    ABV line and §4.23(d) REQUIRES it — the first-percent-line locator read
    label ABV as 60% and went red across a class boundary."""
    fs = _wine_fields(
        ["ABC WINES", "2007", "CALIFORNIA", "60% CHARDONNAY", "40% SEMILLON",
         "ALC. 12.5% BY VOL.", "BOTTLED BY ABC VINTNERS, CITY, STATE", "750 ML",
         "CONTAINS SULFITES"],
        {"beverage_type": "wine", "brand_name": "ABC WINES", "class_type": "Chardonnay",
         "alcohol_content": "12.5%", "net_contents": "750 mL", "vintage": "2007",
         "appellation": "California", "grape_varietals": "chardonnay/semillon"})
    assert fs["alcohol_content"]["status"] == "MATCH"
    assert "12.5" in fs["alcohol_content"]["label_value"]
    # p.10-8: blend prose ('blend of 50% MERLOT and…') above the ABV line
    fs8 = _wine_fields(
        ["ABC WINERY", "AMERICAN RED WINE", "This red wine is a blend of 50% MERLOT and",
         "50% CABERNET SAUVIGNON. We find it", "quite yummy.", "ALC. 13% BY VOL.",
         "BOTTLED BY XYZ CELLARS, CITY, STATE", "CONTAINS SULFITES", "750 ML"],
        {"beverage_type": "wine", "brand_name": "ABC WINERY",
         "class_type": "American Red Wine", "alcohol_content": "13%",
         "net_contents": "750 mL"})
    assert fs8["alcohol_content"]["status"] == "MATCH"


def test_bam_bare_percent_still_locates_without_context():
    """No ALC/VOL context anywhere → the fallback keeps the old first-line
    behavior rather than losing the statement entirely."""
    fs = _wine_fields(["SEABREEZE CELLARS", "California Chardonnay — Table Wine",
                       "12.5%", "750 mL", "Contains Sulfites",
                       "Vinted and bottled by Seabreeze Cellars, Napa, California"],
                      _WINE_APP_FULL)
    assert fs["alcohol_content"]["status"] == "MATCH"


def test_table_light_designation_is_word_bounded():
    """'Moonlight Cellars' / 'Twilight Zinfandel' are brands, not light-wine
    designations — substring matching excused a mandatory ABV statement."""
    req, _ = abv_required(BevType.WINE, "Moonlight Cellars Red")
    assert req is True
    req, _ = abv_required(BevType.WINE, "Twilight Zinfandel")
    assert req is True
    req, _ = abv_required(BevType.WINE, "Light Rice Wine")
    assert req is False


def test_bam_bottler_name_serves_as_brand():
    """BAM p.10-2: no separate brand line — the bottler's name IS the brand
    (§4.33(a)). Found-inside-the-bottled-by-line must match, not review."""
    lines = ["RED TABLE WINE", "BOTTLED BY XYZ WINERY, CITY, STATE", *_BAM_WARN,
             "CONTAINS SULFITES", "750 ML"]
    fs = _wine_fields(lines, {"beverage_type": "wine", "brand_name": "XYZ WINERY",
                              "class_type": "Red Table Wine", "alcohol_content": "12.5%",
                              "net_contents": "750 mL"})
    assert fs["brand_name"]["status"] == "MATCH"
    assert fs["brand_name"]["citation"] == "27 CFR §4.33(a)"
    # a brand genuinely absent from the label stays a review item
    fs2 = _wine_fields(lines, {"beverage_type": "wine", "brand_name": "OTHER ESTATE",
                               "class_type": "Red Table Wine", "alcohol_content": "12.5%",
                               "net_contents": "750 mL"})
    assert fs2["brand_name"]["status"] == "NEEDS_REVIEW"


def test_bam_sparse_front_panel_combined_floor():
    """BAM p.10-6 (imported + strip label): the front is brand + vintage +
    artwork. Per-panel flooring called it 'not a label' and dropped its words
    — brand/vintage went not_found despite being printed."""
    from api.verify import verify_multi
    front = _label_words(["DOWNUNDER WINERY", "2007"])
    strip = _label_words(["RED WINE   VICTORIA   12% ALC./VOL.",
                          "IMPORTED BY OZ IMPORTS, CITY, STATE",
                          "PRODUCT OF AUSTRALIA   750 ML"])
    back = _label_words([*_BAM_WARN, "CONTAINS SULFITES"])
    app = {"beverage_type": "wine", "brand_name": "DOWNUNDER WINERY",
           "class_type": "Red Wine", "alcohol_content": "12%", "net_contents": "750 mL",
           "vintage": "2007", "appellation": "Victoria", "origin": "Australia"}
    r = verify_multi([(front, None), (strip, None), (back, None)], app)
    fs = {f["field"]: f for f in r["fields"]}
    assert "image" not in fs                       # no 'not a label' noise
    assert fs["brand_name"]["status"] == "MATCH"
    assert fs["vintage"]["status"] == "MATCH"
    assert r["screening_result"] == "no_mismatch_found"
    # a single sparse image is still floored (nothing to combine with)
    from api.verify import verify
    r1 = verify(_label_words(["DOWNUNDER WINERY"]), app)
    assert r1["screening_result"] == "screening_incomplete"


# ── part 7 malt audit (docs/research/malt-labeling-audit-ttb.md, M-1..M-9) ───

_MALT_APP = {"beverage_type": "malt_beverage", "brand_name": "IRON HARBOR BREWING CO.",
             "class_type": "American Pale Ale", "alcohol_content": "5.6%",
             "net_contents": "12 FL OZ"}
_MALT_LINES = ["IRON HARBOR BREWING CO.", "American Pale Ale", "5.6% ALC/VOL",
               "12 FL OZ", "BREWED AND CANNED BY IRON HARBOR BREWING CO.",
               "PORTLAND, MAINE"]


def test_malt_range_statement_is_prohibited():
    """§7.65(b): malt alcohol content may not be a range or max/min — the
    statement itself is the defect, even when the application falls inside."""
    v, note = compare_abv(5.0, parse_abv("4% to 6% alc/vol"), BevType.MALT)
    assert v == AbvVerdict.MISMATCH and "range" in note


def test_malt_format_legality():
    assert abv_format_legality("5.6% ABV", BevType.MALT)[0] == "FAIL"
    assert abv_format_legality("4.4% ABW", BevType.MALT)[0] == "FAIL"
    assert abv_format_legality("5.25% ALC/VOL", BevType.MALT)[0] == "FAIL"   # nearest 0.1 at 0.5%+
    assert abv_format_legality("0.25% ALC/VOL", BevType.MALT)[0] == "PASS"   # hundredths OK under 0.5
    assert abv_format_legality("5.6% ALC/VOL", BevType.MALT)[0] == "PASS"
    assert abv_format_legality("ALC. 5.6% BY VOL.", BevType.MALT)[0] == "PASS"
    assert abv_format_legality("5.6% ABV", BevType.SPIRITS) is None          # spirits unasserted


def test_malt_brewed_canned_by_matches_and_absence_is_not_amber():
    """§7.66: the explanatory phrase is OPTIONAL for malt — found phrase is a
    positive MATCH ('BREWED AND CANNED BY' was invisible to the old regex);
    absence is NOT_CHECKED (grey), never a review item."""
    fs = _wine_fields(_MALT_LINES, _MALT_APP)
    assert fs["name_address"]["status"] == "MATCH"
    bare = _wine_fields(_MALT_LINES[:4] + ["PORTLAND, MAINE"], _MALT_APP)
    assert bare["name_address"]["status"] == "NOT_CHECKED"


def test_malt_sulfites_silent_when_absent_flagged_when_negative():
    fs = _wine_fields(_MALT_LINES, _MALT_APP)
    assert "sulfite_declaration" not in fs           # absence is normal for malt
    pos = _wine_fields([*_MALT_LINES, "CONTAINS SULFITES"], _MALT_APP)
    assert pos["sulfite_declaration"]["status"] == "MATCH"
    neg = _wine_fields([*_MALT_LINES, "SULFITE FREE"], _MALT_APP)
    assert neg["sulfite_declaration"]["status"] == "NEEDS_REVIEW"
    assert neg["sulfite_declaration"]["reason_code"] == "sulfite_negative_claim"


def test_malt_aspartame_declaration_form():
    ok = _wine_fields([*_MALT_LINES, "PHENYLKETONURICS: CONTAINS PHENYLALANINE."], _MALT_APP)
    assert ok["aspartame_declaration"]["status"] == "MATCH"
    bad = _wine_fields([*_MALT_LINES, "Contains aspartame"], _MALT_APP)
    assert bad["aspartame_declaration"]["status"] == "NEEDS_REVIEW"
    none = _wine_fields(_MALT_LINES, _MALT_APP)
    assert "aspartame_declaration" not in none       # absence proves nothing


def test_malt_net_contents_form():
    from api.rules.malt import malt_net_form
    from api.rules.net_contents import parse_net_ml
    assert malt_net_form("12 FL OZ", parse_net_ml("12 FL OZ")) is None
    assert malt_net_form("1 PINT 0.9 FL. OZ.", parse_net_ml("1 PINT 0.9 FL. OZ.")) is None
    assert malt_net_form("355 mL", parse_net_ml("355 mL"))[0] == "metric_only_net"
    assert malt_net_form("16 FL OZ", parse_net_ml("16 FL OZ"))[0] == "net_form"
    # verify-level: agreeing 16 FL OZ still escalates to amber form review
    fs = _wine_fields([*_MALT_LINES[:3], "16 FL OZ", *_MALT_LINES[4:]],
                      {**_MALT_APP, "net_contents": "16 FL OZ"})
    assert fs["net_contents"]["status"] == "NEEDS_REVIEW"
    assert fs["net_contents"]["reason_code"] == "net_form"


def test_varietal_percentages_must_total_100():
    lines = ["ABC WINES", "CALIFORNIA", "60% CHARDONNAY", "45% SEMILLON",
             "ALC. 12.5% BY VOL.", "BOTTLED BY ABC VINTNERS, CITY, STATE",
             "750 ML", "CONTAINS SULFITES"]
    app = {"beverage_type": "wine", "brand_name": "ABC WINES", "class_type": "Chardonnay",
           "alcohol_content": "12.5%", "net_contents": "750 mL",
           "appellation": "California", "grape_varietals": "chardonnay/semillon"}
    fs = _wine_fields(lines, app)
    assert fs["grape_varietals"]["status"] == "NEEDS_REVIEW"
    assert fs["grape_varietals"]["reason_code"] == "varietal_percentages_sum"
    assert "105" in fs["grape_varietals"]["note"]
    # 60/40 totals 100 — stays green
    ok = _wine_fields([l.replace("45%", "40%") for l in lines], app)
    assert ok["grape_varietals"]["status"] == "MATCH"

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
    assert panels == [("https://x/f.jpg", "front", ""), ("https://x/b.jpg", "back", "")]
    # front-only COLA: one panel, no invented back
    assert pick_panels({"images": [{"image_url": "https://x/f.jpg",
                                    "container_position": "front"}]}) == [("https://x/f.jpg", "front", "")]
    # no positions at all → falls back to pick_image
    assert pick_panels({"main_image_url": "https://x/m.jpg"}) == [("https://x/m.jpg", "main", "")]
    # declared original dims ride along when the API provides them
    assert pick_panels({"images": [{"image_url": "u", "container_position": "front",
                                    "width_pixels": 731, "height_pixels": 993}]}) \
        == [("u", "front", "731x993")]


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

    items = [{"file_name": "a_front.jpg", "state": "done",
              "verification_status": "done_red", "final_status": "done_green",
              "review_complete": True, "elapsed_ms": 2450,
              "registry": {"fanciful_name": "Pelopee", "origin": "france"},
              "override": {"value": "PASS", "at": "2026-07-31 22:00",
                           "original": "Mismatch found"},
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
    assert s["items"][0]["override"]["value"] == "PASS"
    assert s["items"][0]["override"]["at"] == "2026-07-31 22:00"
    assert s["items"][0]["verification_status"] == "done_red"    # machine verdict kept
    assert s["items"][0]["final_status"] == "done_green"         # after agent decision
    assert s["items"][0]["review_complete"] is True
    assert s["items"][0]["elapsed_ms"] == 2450
    assert s["items"][0]["registry"]["fanciful_name"] == "Pelopee"
    assert s["items"][1]["registry"] is None
    assert s["items"][1]["review_complete"] is False
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


# ── engineering-review regressions (2026-08-01) ──────────────────────────────

def test_three_digit_proof_parses():
    """100+ proof spirits are routine; \\d{1,2} misparsed '100 PROOF' as proof=0
    → false INCONSISTENT for every bottled-in-bond bourbon."""
    r = parse_abv("50% ALC/VOL (100 PROOF)")
    assert r.percent == 50.0 and r.proof == 100.0
    ok, _ = proof_consistency(r)
    assert ok is True
    r2 = parse_abv("101 PROOF")
    assert r2.proof == 101.0 and r2.percent == 50.5


def test_merge_mismatch_survives_not_required():
    """A wrong value PRINTED on one panel is a finding; legal absence on the
    other panel must not erase it (NOT_REQUIRED used to outrank MISMATCH)."""
    from api.verify import _MERGE_RANK
    assert _MERGE_RANK["MISMATCH"] > _MERGE_RANK["NOT_REQUIRED"]
    assert _MERGE_RANK["MATCH"] > _MERGE_RANK["MISMATCH"]      # found-correct still wins
    assert _MERGE_RANK["NOT_REQUIRED"] > _MERGE_RANK["NEEDS_REVIEW"]


def test_unknown_beverage_type_never_500s():
    from api.verify import verify
    result = verify([], {"beverage_type": "cider"})            # falls back to strictest
    assert result["screening_result"] == "screening_incomplete"


def test_locator_tie_semantics():
    """The same text printed twice (brand + bottled-by line) is NOT ambiguous —
    either pick yields the same verdict. A different READING tying the score
    (scrambled word order under token_sort) IS ambiguous; the old strict '<'
    silently dropped exact-tie rivals."""
    from api.locator import Locator, Word
    dup = [Word("RESERVE", (10, 10, 100, 30), 0.95),
           Word("RESERVE", (10, 200, 100, 220), 0.95)]
    r = Locator(dup).find("RESERVE")
    assert r.found and not r.ambiguous
    scrambled = [Word("OLD", (10, 10, 60, 30), 0.95), Word("TOM", (70, 10, 120, 30), 0.95),
                 Word("TOM", (10, 300, 60, 320), 0.95), Word("OLD", (70, 300, 120, 320), 0.95)]
    r2 = Locator(scrambled).find("OLD TOM")
    assert r2.found and r2.ambiguous


def test_corrupt_manifest_refuses_instead_of_wiping(tmp_path):
    from api.eval.colacloud_pipeline import _load_manifest, _save_manifest
    d = tmp_path / "wine"; d.mkdir()
    (d / "manifest.json").write_text("{ not json")
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="corrupt"):
        _load_manifest(d)
    # atomic save leaves no .tmp behind
    _save_manifest(d, [{"id": "1", "file": "x.jpg"}])
    assert not (d / "manifest.json.tmp").exists()
    assert _load_manifest(d)[0]["id"] == "1"


# ── complete-review regressions (red team, 2026-08-01) ───────────────────────

def test_net_contents_restatement_not_summed():
    """'12 FL OZ (355 mL)' is ONE declaration restated — the most common label
    format; summing it double-counted to 710 mL → false MISMATCH on every
    standard beer can. Genuine compounds still sum."""
    assert abs(parse_net_ml("12 FL OZ (355 ML)") - 355) < 1
    assert compare_net("355 mL", "NET CONTENTS 12 FL OZ (355 ML)")[0] == "MATCH"
    assert abs(parse_net_ml("1 PINT 0.9 FL. OZ.") - 499.8) < 0.5   # compound sums
    assert compare_net("750 mL", "750 ML (25.4 FL OZ)")[0] == "MATCH"


def test_net_contents_keg_units():
    """Registry pulls emit QT/GAL/BBL for kegged beer — previously unparseable
    (every keg COLA landed NEEDS_REVIEW)."""
    assert parse_net_ml("1 QT") == 946.4
    assert parse_net_ml("1 GAL") == 3785.4
    assert parse_net_ml("1 BBL") == 117347.8
    assert compare_net("1 GAL", "1 GALLON")[0] == "MATCH"


def test_agave_percent_not_abv():
    """'100% AGAVE' matched as '00%' → ABV 0.0 → false mismatch + false proof
    inconsistency on every tequila label. \\b guard; proof-only conversion
    still yields the right percent."""
    r = parse_abv("TEQUILA 100% AGAVE 80 PROOF")
    assert r.proof == 80.0 and r.percent == 40.0        # derived from proof, not "00%"
    ok, _ = proof_consistency(r)
    assert ok is not False


def test_merged_government_warning_anchor():
    """OCR merges 'GOVERNMENTWARNING:' — the anchor must still fire (the
    containment compare was space-insensitive but the gate wasn't)."""
    from api.rules.warning import PREFIX_ANY_RE, PREFIX_CAPS_RE
    assert PREFIX_ANY_RE.search("GOVERNMENTWARNING: (1) ACCORDING")
    assert PREFIX_CAPS_RE.search("GOVERNMENTWARNING:")
    r = validate_warning("GOVERNMENTWARNING: " + STATUTORY_WARNING.split(": ", 1)[1])
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS


def test_warning_block_survives_ocr_word_splits():
    """44-token cap truncated compliant warnings when OCR split words (statute
    is 42 words); cap now 60 — the gap rule is the real terminator."""
    from api.locator import Locator, Word
    toks = STATUTORY_WARNING.replace("machinery,", "machin ery,").replace(
        "beverages", "bev erages").split()
    words = [Word(t, (10 + (i % 5) * 90, 10 + (i // 5) * 24,
                      90 + (i % 5) * 90, 30 + (i // 5) * 24), 0.95)
             for i, t in enumerate(toks)]
    loc = Locator(words)
    w = loc.find_warning()
    assert w.found
    r = validate_warning(w.text)
    assert r.outcomes[SubCheck.TEXT] == Outcome.PASS


def test_internal_consistency_merge_worst_wins():
    """An inconsistent proof/ABV pair PRINTED on any panel is a §5.65
    violation — a consistent pair on the other panel must not mask it."""
    from api.locator import Word
    from api.verify import verify_multi
    mk = lambda lines: [Word(w, (10 + i * 90, 10 + j * 30, 90 + i * 90, 28 + j * 30), 0.95)
                        for j, t in enumerate(lines) for i, w in enumerate(t.split())]
    good = mk(["OLD TOM DISTILLERY", "45% ALC/VOL (90 PROOF)"])
    bad = mk(["OLD TOM DISTILLERY", "45% ALC/VOL (80 PROOF)"])
    app = {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM DISTILLERY",
           "alcohol_content": "45% Alc./Vol."}
    merged = verify_multi([(good, None), (bad, None)], app)
    by = {f["field"]: f["status"] for f in merged["fields"]}
    assert by["internal_consistency"] == "MISMATCH"


def test_cross_line_proof_consistency():
    """% and proof on separate lines: the §5.65(c) cross-check must still run
    (it silently skipped whenever they weren't co-located)."""
    from api.locator import Word
    from api.verify import verify
    words = [Word(w, (10 + i * 90, 10 + j * 30, 90 + i * 90, 28 + j * 30), 0.95)
             for j, t in enumerate(["OLD TOM DISTILLERY", "45% ALC/VOL", "80 PROOF"])
             for i, w in enumerate(t.split())]
    r = verify(words, {"beverage_type": "distilled_spirits",
                       "brand_name": "OLD TOM DISTILLERY",
                       "alcohol_content": "45% Alc./Vol."})
    by = {f["field"]: f for f in r["fields"]}
    assert "internal_consistency" in by
    assert by["internal_consistency"]["status"] == "MISMATCH"   # 45% vs 80 proof


# ── European diacritics (Château Le Coteau case, 2026-08-02) ─────────────────

def test_fold_diacritics():
    from api.rules.normalize import ascii_loose, fold_diacritics
    assert fold_diacritics("Château") == "Chateau"
    assert fold_diacritics("Pélopée") == "Pelopee"
    assert fold_diacritics("Contrôlée") == "Controlee"
    assert ascii_loose("Château le Coteau") == ascii_loose("Chateau Le Coteau")


def test_brand_diacritics_is_special_warning():
    from api.locator.locator import Locator, Word
    from api.verify import _text_field_one
    words = [Word("Château", (0, 0, 90, 20), 0.95),
             Word("le", (95, 0, 115, 20), 0.95),
             Word("Coteau", (120, 0, 200, 20), 0.95)]
    r = _text_field_one("brand_name", "Chateau Le Coteau", Locator(words))
    assert r.status == "LIKELY_MATCH"
    assert r.reason_code == "diacritics_differ"
    assert "Château le Coteau" in (r.label_value or "")
    assert "accent" in r.note.lower()


def test_multi_panel_tie_prefers_located_text():
    from api.locator.locator import Word
    from api.verify import verify_multi
    # front: unrelated words (brand not found); back: the accented brand
    front = [Word("MARGAUX", (0, 0, 100, 20), 0.95),
             Word("RED", (0, 30, 40, 50), 0.95),
             Word("WINE", (45, 30, 100, 50), 0.95),
             Word("FRANCE", (0, 60, 100, 80), 0.95)]
    back = [Word("Château", (0, 0, 90, 20), 0.95),
            Word("le", (95, 0, 115, 20), 0.95),
            Word("Coteau", (120, 0, 200, 20), 0.95),
            Word("RED", (0, 30, 40, 50), 0.95),
            Word("WINE", (45, 30, 100, 50), 0.95)]
    r = verify_multi([(front, None), (back, None)],
                     {"beverage_type": "wine", "brand_name": "Chateau Le Coteau"})
    bn = next(f for f in r["fields"] if f["field"] == "brand_name")
    assert bn["status"] == "LIKELY_MATCH"
    assert bn["reason_code"] == "diacritics_differ"
    assert bn["label_value"] == "Château le Coteau"
