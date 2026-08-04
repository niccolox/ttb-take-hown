"""OpenAI summary layer evaluated against golden-corpus cases.

Two tiers, mirroring the OCR eval pattern:
- Fast tier (always runs, hermetic): real verify() results from golden-
  mirroring word fixtures flow through the prompt builder, the
  deterministic record, the contradiction check, and the endpoint (fake
  model) — asserting the record's honesty invariants case by case.
- Live tier (LABELCHECK_OPENAI_EVAL=1): the same results against the real
  Azure endpoint — whatever the model does (drafts, thinks itself to
  death, errors), the response must always be a valid record that never
  contradicts the verdicts. The deterministic fallback makes that a hard
  guarantee worth pinning.
"""

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from api.locator import Word
from api.rules.warning import STATUTORY_WARNING
from api.summary import (build_user_prompt, contradicts, decisions_trailer,
                        deterministic_record, quality_facts)
from api.verify import verify


def _words(lines, start_y=10):
    out, y = [], start_y
    for text in lines:
        x = 10
        for w in text.split():
            out.append(Word(w, (x, y, x + len(w) * 12, y + 20), 0.96))
            x += len(w) * 12 + 8
        y += 28
    return out


def _warning_lines(title_case=False):
    text = STATUTORY_WARNING
    if title_case:
        text = text.replace("GOVERNMENT WARNING:", "Government Warning:")
    return textwrap.wrap(text, 46)


SPIRITS_APP = {"beverage_type": "distilled_spirits", "brand_name": "OLD TOM DISTILLERY",
               "class_type": "Kentucky Straight Bourbon Whiskey",
               "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}

# golden-mirroring cases: (name, label lines, application, expectation)
CASES = {
    "spirits_clean": dict(
        lines=["OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
               "45% Alc./Vol. (90 Proof)", "750 mL", *_warning_lines()],
        app=SPIRITS_APP, expect="all_green"),
    "trap_titlecase": dict(
        lines=["OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
               "45% Alc./Vol. (90 Proof)", "750 mL", *_warning_lines(title_case=True)],
        app=SPIRITS_APP, expect="warning_red"),
    "trap_abv_outside": dict(
        lines=["OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
               "46% Alc./Vol. (92 Proof)", "750 mL", *_warning_lines()],
        app=SPIRITS_APP, expect="abv_red"),
    "wine_table_no_abv": dict(
        lines=["SEABREEZE CELLARS", "California Chardonnay — Table Wine",
               "750 mL", "Contains Sulfites",
               "Vinted and bottled by Seabreeze Cellars, Napa, California",
               *_warning_lines()],
        app={"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
             "class_type": "California Chardonnay — Table Wine",
             "alcohol_content": "12.5%", "net_contents": "750 mL"},
        expect="not_required_green"),
}


@pytest.fixture(scope="module")
def golden_results():
    return {name: verify(_words(c["lines"]), c["app"]) for name, c in CASES.items()}


def test_golden_fixtures_behave_like_their_goldens(golden_results):
    r = golden_results
    assert r["spirits_clean"]["screening_result"] == "no_mismatch_found"
    warn = next(f for f in r["trap_titlecase"]["fields"]
                if f["field"] == "government_warning")
    assert warn["status"] == "MISMATCH"
    abv = next(f for f in r["trap_abv_outside"]["fields"]
               if f["field"] == "alcohol_content")
    assert abv["status"] == "MISMATCH"
    abv_w = next(f for f in r["wine_table_no_abv"]["fields"]
                 if f["field"] == "alcohol_content")
    assert abv_w["status"] == "NOT_REQUIRED"


def test_prompts_carry_golden_facts_faithfully(golden_results):
    for name, result in golden_results.items():
        p = build_user_prompt(result["fields"], CASES[name]["app"], "t",
                              result=result, decision="PASS")
        for f in result["fields"]:
            assert f["status"] in p            # every status verbatim
        assert "<untrusted>" in p              # applicant values stay fenced


def test_deterministic_records_per_golden(golden_results):
    r = golden_results
    rec = deterministic_record(r["trap_titlecase"]["fields"], "t",
                               {"whole": {"value": "FAIL", "original": "Needs correction"}},
                               r["trap_titlecase"], "FAIL")
    assert "- Government Warning: MISMATCH" in rec
    assert "Clean checks:" in rec              # the greens stay grouped
    rec2 = deterministic_record(r["spirits_clean"]["fields"], "t", {},
                                r["spirits_clean"], "PASS")
    assert "MISMATCH" not in rec2
    assert "Machine-verified clean" in rec2
    rec3 = deterministic_record(r["wine_table_no_abv"]["fields"], "t", {},
                                r["wine_table_no_abv"], "PASS")
    assert "Alcohol content" in rec3           # NOT_REQUIRED counts as clean
    assert "- Alcohol content: NOT_REQUIRED" not in rec3


def test_contradiction_semantics_per_golden(golden_results):
    r = golden_results
    # clean golden: failure language in a PASS draft must be dropped
    assert contradicts(r["spirits_clean"]["fields"],
                       "the warning failed to match") is True
    # trap golden: the fields carry the MISMATCH, so naming it is legal
    assert contradicts(r["trap_titlecase"]["fields"],
                       "machine found a mismatch on the warning") is False


def test_endpoint_round_trip_on_golden_result(golden_results, monkeypatch):
    from fastapi.testclient import TestClient
    from api import main
    from api.jobs import ResultStore

    result = dict(golden_results["trap_abv_outside"])
    result["request_id"] = "golden-1"
    store = ResultStore()
    store.put(result)

    class Draft:
        model = "fake"
        def available(self): return True
        def complete(self, s, u):
            assert "MISMATCH" in u             # golden fact reached the model
            return ("- Alcohol content: MISMATCH — label 46% vs application 45%\n"
                    "- Clean checks: brand, class, net contents, warning")

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "azoai_client", Draft())
    client = TestClient(main.app)
    body = client.post("/api/verify/golden-1/summary",
                       json={"decision": "FAIL", "at": "t"}).json()
    assert body["text"].startswith("- Alcohol content: MISMATCH")
    assert "Whole label: FAIL recorded t" in body["text"]


@pytest.mark.skipif(not os.environ.get("LABELCHECK_OPENAI_EVAL"),
                    reason="set LABELCHECK_OPENAI_EVAL=1 (needs AZ_OPENAI_* env) for the live eval")
def test_live_model_records_hold_invariants(golden_results):
    """Whatever the live model does — drafts, deliberates itself to empty,
    or fails — the layer must yield a record that never contradicts the
    golden verdicts. Runs each golden through the real client."""
    from api.azure_openai import AzureOpenAIClient
    from api.summary import SYSTEM_FAIL, SYSTEM_PASS

    client = AzureOpenAIClient()
    if not client.available():
        pytest.skip("AZ_OPENAI_* not configured")
    for name, result in golden_results.items():
        red = any(f["status"] == "MISMATCH" for f in result["fields"])
        decision = "FAIL" if red else "PASS"
        prompt = build_user_prompt(result["fields"], CASES[name]["app"], "t",
                                   result=result, decision=decision)
        text = client.complete(SYSTEM_FAIL if red else SYSTEM_PASS, prompt)
        if not text:                            # thinker exhausted — fallback rules
            text = deterministic_record(result["fields"], "t", {}, result, decision)
        record = text + "\n\n" + decisions_trailer(result["fields"], {}, "t",
                                                   decision=decision)
        assert record.strip(), name
        if decision == "PASS":
            assert not contradicts(result["fields"], text), \
                f"{name}: live draft contradicts the golden verdicts: {text[:200]}"
        assert f"Whole label: {decision}" in record, name
