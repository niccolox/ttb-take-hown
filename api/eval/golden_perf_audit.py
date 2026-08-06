"""Golden-corpus screening + cross-check performance audit.

Runs every golden through the live server measuring the two-tier story:
- SCREENING (fast path): wall-clock to provisional, server timing_ms,
  provisional statuses, the <5 s promise.
- CROSS-CHECK (J1/J2/mm): wall-clock to settled, revisions, per-field
  refinements (downgrades/upgrades/annotations/mm-rereads), guard
  states, mm second-read verdicts.
- CORRECTNESS: final screening_result + key field status vs the
  manifest expectation (encoded below per golden).

Usage (server up): .venv/bin/python -m api.eval.golden_perf_audit
Writes api/eval/results/golden-perf-audit.json.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from api.eval.measure_troubled import corpora, post_verify  # noqa: E402

BASE = "http://localhost:8123"

# expectation per golden: (field, wanted-statuses) plus overall class.
# GREEN = no_mismatch; RED = mismatch_found; AMBER = review-class overall.
EXPect = {
    "spirits_clean":         {"overall": "GREEN"},
    "malt_clean":            {"overall": "GREEN"},
    "wine_no_abv_table":     {"field": ("alcohol_content", {"NOT_REQUIRED"})},
    "trap_titlecase_warning": {"overall": "RED",
                               "field": ("government_warning", {"MISMATCH"})},
    "trap_word_substitution": {"overall": "RED",
                               "field": ("government_warning", {"MISMATCH"})},
    "trap_all_bold_warning": {"field": ("government_warning",
                                        {"MISMATCH", "NEEDS_REVIEW"})},
    "trap_missing_warning":  {"field": ("government_warning",
                                        {"MISMATCH", "NEEDS_REVIEW"})},
    "trap_abv_within_band":  {"field": ("alcohol_content",
                                        {"WITHIN_TOLERANCE"})},
    "trap_abv_outside_band": {"overall": "RED",
                              "field": ("alcohol_content", {"MISMATCH"})},
    "photo_skew":            {"not_overall": "RED"},
    "photo_glare":           {"not_overall": "RED"},
    "photo_blur_dark":       {"not_overall": "RED"},
    "photo_curved":          {"not_overall": "RED"},
    "photo_lowres":          {"not_overall": "RED"},
    "decorative_font":       {"not_overall": "RED"},
}
GREEN_RESULTS = {"no_mismatch_found"}
RED_RESULTS = {"mismatch_found"}


def wait_settled(rid: str, budget_s: float = 120.0):
    t0 = time.monotonic()
    body = None
    while time.monotonic() - t0 < budget_s:
        import urllib.request
        try:
            with urllib.request.urlopen(f"{BASE}/api/verify/{rid}",
                                        timeout=30) as r:
                body = json.load(r)
        except OSError:
            time.sleep(1)
            continue
        if body.get("settled"):
            # grace for the post-settle mm attach path (rides J3 pre-settle
            # normally, but don't race a slow provider)
            return body, time.monotonic() - t0
        time.sleep(0.5)
    return body, time.monotonic() - t0


def classify_overall(sr: str) -> str:
    return "GREEN" if sr in GREEN_RESULTS else \
           "RED" if sr in RED_RESULTS else "AMBER"


def check(gid: str, body: dict) -> tuple[bool, str]:
    exp = EXPect.get(gid, {})
    sr = body.get("screening_result", "?")
    cls = classify_overall(sr)
    fields = {f["field"]: f for f in body.get("fields", [])}
    if "overall" in exp and cls != exp["overall"]:
        return False, f"overall {cls} (wanted {exp['overall']})"
    if "not_overall" in exp and cls == exp["not_overall"]:
        return False, f"overall {cls} (must not be {exp['not_overall']})"
    if "field" in exp:
        name, wanted = exp["field"]
        got = fields.get(name, {}).get("status")
        if got not in wanted:
            return False, f"{name}={got} (wanted {'/'.join(sorted(wanted))})"
    return True, "as expected"


def main():
    goldens = next(items for name, items in corpora() if name == "golden")
    rows, prov_ms, settle_s = [], [], []
    for item in goldens:
        gid = item["id"].split("/", 1)[1]
        t0 = time.monotonic()
        first = post_verify(BASE, item)
        wall_prov = (time.monotonic() - t0) * 1000
        if first is None:
            rows.append({"id": gid, "error": "verify failed"})
            continue
        body, wall_settle = wait_settled(first["result_id"])
        body = body or first
        ok, why = check(gid, body)
        refin = {}
        mm = {}
        guards = {}
        for f in body.get("fields", []):
            for r in f.get("refinements", []):
                refin[r["kind"]] = refin.get(r["kind"], 0) + 1
            if f.get("mm_reread"):
                mm[f["field"]] = f["mm_reread"].get("verdict")
            g = f.get("guard")
            if g:
                guards[f["field"]] = g.get("state")
        prov_ms.append(wall_prov)
        settle_s.append(wall_settle)
        rows.append({
            "id": gid, "ok": ok, "why": why,
            "screening_result": body.get("screening_result"),
            "provisional_wall_ms": round(wall_prov),
            "server_total_ms": (first.get("timing_ms") or {}).get("total"),
            "settle_wall_s": round(wall_settle, 1),
            "revision": body.get("revision"),
            "refinements": refin, "guards": guards, "mm": mm,
        })
        print(f"{gid}: ok={ok} prov={wall_prov:.0f}ms settle={wall_settle:.1f}s "
              f"sr={body.get('screening_result')} mm={mm} ({why})")

    out = {
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "promise_5s": {"provisional_max_ms": round(max(prov_ms)),
                       "violations": sum(1 for v in prov_ms if v > 5000)},
        "provisional_ms": {"p50": round(statistics.median(prov_ms)),
                           "max": round(max(prov_ms))},
        "settle_s": {"p50": round(statistics.median(settle_s), 1),
                     "max": round(max(settle_s), 1)},
        "expectation_failures": [r for r in rows if not r.get("ok", True)],
        "rows": rows,
    }
    dest = REPO / "api" / "eval" / "results" / "golden-perf-audit.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    print(f"provisional p50={out['provisional_ms']['p50']}ms "
          f"max={out['provisional_ms']['max']}ms "
          f"(<5s violations: {out['promise_5s']['violations']})")
    print(f"settle p50={out['settle_s']['p50']}s max={out['settle_s']['max']}s")
    fails = out["expectation_failures"]
    print(f"expectation failures: {len(fails)}: "
          f"{[(f['id'], f['why']) for f in fails]}")


if __name__ == "__main__":
    main()
