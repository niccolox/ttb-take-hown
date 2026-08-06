"""mm second-read precision ship-gate (mm-ocr-augment T14 / D-5).

Measures, against a LIVE multimodal provider, whether the
sides_with_application headline can be trusted: of all rows the second
read claims side with the applicant, how many are RIGHT per ground
truth? The chip may not default on anywhere until this passes
(amendment 25):

    precision ≥ 0.80  AND  n ≥ 10 sides_with_application samples

Split (amendment 25): CALIBRATION = the COLA Cloud corpora (registry
records are approved labels — the application value IS on the label, so
sides_with_application there is correct by construction and differs/
agrees calibrate the noise floor). HELD-OUT = the golden traps, where
TRUTH below states explicitly whether the application value truly
appears on the label (trap labels intentionally differ).

Usage (server up, MM configured with a REAL provider — not fixture):
    LABELCHECK_MM_READ=1 .venv/bin/python api/eval/mm_precision.py \
        [--base http://localhost:8123] [--corpus golden|colacloud|all]
Writes api/eval/results/mm-precision.json and prints the gate verdict.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .measure_troubled import corpora, post_verify, wait_settled

EVAL = Path(__file__).resolve().parent

# Ground truth for the held-out goldens: is the APPLICATION value truly
# printed on the label for the fields that fire? (From the manifest
# truth blocks — trap labels differ from the application on purpose.)
GOLDEN_TRUTH = {
    # (golden id, field): app value actually on label?
    ("golden/trap_abv_outside_band", "alcohol_content"): False,   # label 46 vs app 45
    ("golden/trap_titlecase_warning", "government_warning"): True,   # content words present, typography wrong
    ("golden/trap_word_substitution", "government_warning"): False,  # a statutory word substituted
    ("golden/trap_all_bold_warning", "government_warning"): True,    # content correct, weight wrong
    ("golden/wine_no_abv_table", "brand_name"): True,
    ("golden/photo_lowres", "class_type"): True,
}
PRECISION_FLOOR = 0.80
MIN_N = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8123")
    ap.add_argument("--corpus", default="all",
                    choices=["golden", "colacloud", "all"])
    args = ap.parse_args()

    swa = []          # every sides_with_application observation
    verdicts = {"agrees": 0, "sides_with_application": 0, "differs": 0,
                "unreadable": 0, "error": 0}
    fired = apps = 0
    for corpus, items in corpora():
        tier = "held_out" if corpus == "golden" else "calibration"
        if args.corpus == "golden" and tier != "held_out":
            continue
        if args.corpus == "colacloud" and tier != "calibration":
            continue
        for item in items:
            if not item["paths"]:
                continue
            first = post_verify(args.base, item)
            if first is None:
                continue
            body = wait_settled(args.base, first["result_id"]) or first
            apps += 1
            for f in body.get("fields") or []:
                mm = f.get("mm_reread")
                if not mm:
                    continue
                fired += 1
                v = mm.get("verdict", "error")
                verdicts[v] = verdicts.get(v, 0) + 1
                if v == "sides_with_application":
                    if tier == "calibration":
                        correct = True      # approved COLA: value IS on label
                    else:
                        correct = GOLDEN_TRUTH.get((item["id"], f["field"]))
                    swa.append({"id": item["id"], "field": f["field"],
                                "tier": tier, "correct": correct,
                                "text": (mm.get("text") or "")[:120]})
            print(f"{item['id']}: {sum(1 for f in (body.get('fields') or []) if f.get('mm_reread'))} reads")

    known = [s for s in swa if s["correct"] is not None]
    n = len(known)
    correct = sum(1 for s in known if s["correct"])
    precision = correct / n if n else None
    gate = (n >= MIN_N and precision is not None
            and precision >= PRECISION_FLOOR)
    out = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "apps": apps, "reads_fired": fired, "verdict_histogram": verdicts,
           "swa_n": n, "swa_correct": correct, "precision": precision,
           "floor": PRECISION_FLOOR, "min_n": MIN_N,
           "gate": "PASS" if gate else "FAIL",
           "samples": swa}
    (EVAL / "results" / "mm-precision.json").write_text(json.dumps(out, indent=1))
    print(f"\nreads fired: {fired} across {apps} apps · verdicts {verdicts}")
    if precision is None:
        print(f"GATE: FAIL — zero sides_with_application observations "
              f"(need ≥{MIN_N}); the chip stays off by default")
    else:
        print(f"sides_with_application precision: {correct}/{n} = "
              f"{precision:.0%} (floor {PRECISION_FLOOR:.0%}, min n {MIN_N})")
        print(f"GATE: {'PASS — D-4 may default on' if gate else 'FAIL — chip stays off'}")


if __name__ == "__main__":
    main()
