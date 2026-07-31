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
    # body wording is otherwise correct → text check FAILS too (prefix token differs)
    assert r.outcomes[SubCheck.TEXT] == Outcome.FAIL

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
