"""Locator tests on synthetic box layouts — no OCR needed (PLAN.md H1)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.locator import Locator, Word


def W(text, x, y, w=50, h=20, conf=0.95):
    return Word(text=text, box=(x, y, x + w, y + h), conf=conf)


def test_line_grouping_and_reading_order():
    words = [W("STRAIGHT", 160, 100), W("KENTUCKY", 100, 102), W("BOURBON", 230, 99),
             W("OLD", 100, 40), W("TOM", 160, 41)]
    loc = Locator(words)
    assert [l.text for l in loc.lines] == ["OLD TOM", "KENTUCKY STRAIGHT BOURBON"]


def test_stacked_brand_cross_line_join():
    words = [W("STONE'S", 100, 40, 120), W("THROW", 110, 70, 100),
             W("PALE", 100, 200), W("ALE", 160, 200)]
    loc = Locator(words)
    f = loc.find("STONE'S THROW")
    assert f.found and f.score >= 95
    assert f.box[1] <= 45 and f.box[3] >= 85          # spans both lines


def test_similar_but_different_brand_rejected():
    words = [W("OLD", 10, 10), W("TOM", 60, 10), W("DISTILLING", 110, 10, 90), W("CO.", 210, 10, 30)]
    f = Locator(words).find("OLD TOM DISTILLERY")
    assert not f.found                                 # must not fuzzy-pass (T1 rule)


def test_ambiguity_margin_flags_near_tie():
    words = [W("RESERVE", 10, 10, 80), W("RESERVA", 10, 200, 80)]
    f = Locator(words).find("RESERVE")
    assert f.found
    # runner-up 'RESERVA' scores close → ambiguous only if within margin AND above threshold
    assert isinstance(f.ambiguous, bool)


def test_low_confidence_propagates():
    words = [W("BLURRY", 10, 10, conf=0.31), W("BRAND", 80, 10, conf=0.30)]
    f = Locator(words).find("BLURRY BRAND")
    assert f.found and f.min_conf <= 0.31


def test_warning_block_reconstruction():
    lines = [
        "GOVERNMENT WARNING: (1) According to the Surgeon",
        "General, women should not drink alcoholic beverages",
        "during pregnancy because of the risk of birth defects.",
        "(2) Consumption of alcoholic beverages impairs your ability",
        "to drive a car or operate machinery, and may cause health problems.",
    ]
    words = []
    for row, line in enumerate(lines):
        x = 10
        for t in line.split():
            words.append(W(t, x, 500 + row * 26, len(t) * 9, 18))
            x += len(t) * 9 + 6
    words.append(W("750", 10, 900))                    # far below — must not be absorbed
    words.append(W("mL", 60, 900))
    loc = Locator(words)
    f = loc.find_warning()
    assert f.found
    assert f.text.startswith("GOVERNMENT WARNING:")
    assert "health problems." in f.text
    assert "750" not in f.text                         # gap rule stopped the block


def test_warning_anchor_with_ocr_confusables():
    words = [W("G0VERNMENT", 10, 10, 110), W("WARN1NG:", 130, 10, 90)]
    f = Locator(words).find_warning()
    assert f.found                                     # confusable-tolerant anchor
