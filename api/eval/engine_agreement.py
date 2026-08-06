"""First-vs-second engine performance audit over the E4 telemetry stream.

Primary engine (nemotron) vs QA shadow (paddle): agreement rates per
field, guard vs non-guard, single-read asymmetry (who reads what the
other can't), disagreement direction, and J2 warning-reread concurrence.
Also segments the stream by the golden-audit run windows so the
infer-length change (1024 → 1536) shows up as a measured delta in
cross-engine agreement.

Usage: .venv/bin/python -m api.eval.engine_agreement
Reads api/data/e4-telemetry.jsonl (+ rotated .1 if present); writes
api/eval/results/engine-agreement.json.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "api" / "data"
RESULTS = ROOT / "api" / "eval" / "results"

GREEN = {"MATCH", "LIKELY_MATCH", "WITHIN_TOLERANCE", "NOT_REQUIRED"}
RED = {"MISMATCH"}


def _klass(status: str | None) -> str:
    if status in GREEN:
        return "green"
    if status in RED:
        return "red"
    return "review"


def load_rows() -> list[dict]:
    rows = []
    for name in ("e4-telemetry.jsonl.1", "e4-telemetry.jsonl"):
        p = DATA / name
        if p.is_file():
            for line in p.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "primary" in r and "qa" in r and "ts" in r:
                    rows.append(r)
    return rows


def audit(rows: list[dict]) -> dict:
    j1 = [r for r in rows if r.get("layer") != "warning-reread"]
    j2 = [r for r in rows if r.get("layer") == "warning-reread"]
    out = {"rows": len(rows), "j1_rows": len(j1), "j2_rows": len(j2)}

    def rate(sel):
        n = len(sel)
        return {"n": n,
                "agree": round(sum(r["agree"] for r in sel) / n, 3) if n else None,
                "single_read": round(sum(bool(r.get("single_read")) for r in sel) / n, 3) if n else None}

    out["overall"] = rate(j1)
    out["guard"] = rate([r for r in j1 if r.get("guard")])
    out["non_guard"] = rate([r for r in j1 if not r.get("guard")])
    out["per_field"] = {f: rate([r for r in j1 if r["field"] == f])
                        for f in sorted({r["field"] for r in j1})}

    # disagreement direction: which engine is the stricter voice?
    direction = Counter()
    for r in j1:
        if r["agree"]:
            continue
        direction[f"{_klass(r['primary']['status'])}->"
                  f"{_klass(r['qa']['status'])}"] += 1
    out["disagreement_direction"] = dict(direction.most_common())

    # single-read asymmetry: who read something the other engine missed?
    single = Counter()
    for r in j1:
        if not r.get("single_read"):
            continue
        p_green = _klass(r["primary"]["status"]) == "green"
        single["primary_read_qa_blank" if p_green else
               "qa_read_primary_blank"] += 1
    out["single_read_direction"] = dict(single)

    # J2 warning-reread concurrence (AD-20: upgrades need J1 agreement)
    if j2:
        out["j2_concurrence"] = {
            "n": len(j2),
            "agree_rate": round(sum(r["agree"] for r in j2) / len(j2), 3),
            "reread_status_mix": dict(Counter(
                r["primary"]["status"] for r in j2).most_common())}
    return out


def window_of(results_file: str, minutes: float = 15.0):
    p = RESULTS / results_file
    if not p.is_file():
        return None
    end = time.mktime(time.strptime(
        json.loads(p.read_text())["measured_at"], "%Y-%m-%d %H:%M:%S"))
    return (end - minutes * 60, end)


def main():
    rows = load_rows()
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "all_time": audit(rows)}

    # golden-audit windows: the infer-length A/B, anchored to each run's
    # measured_at stamp (runs are short; 15-minute lookback bounds them)
    for label, fname in (("golden_1024", "golden-perf-infer1024.json"),
                         ("golden_1536", "golden-perf-infer1536.json"),
                         ("golden_adopted_1536", "golden-perf-audit.json")):
        w = window_of(fname)
        if not w:
            continue
        sel = [r for r in rows if w[0] <= r["ts"] <= w[1]]
        report[label] = audit(sel)

    dest = RESULTS / "engine-agreement.json"
    dest.write_text(json.dumps(report, indent=1))
    print(f"wrote {dest}\n")

    a = report["all_time"]
    print(f"ALL-TIME (n={a['j1_rows']} field pairs, {a['j2_rows']} rereads)")
    print(f"  agreement: overall {a['overall']['agree']:.1%} · "
          f"guard {a['guard']['agree']:.1%} (n={a['guard']['n']}) · "
          f"non-guard {a['non_guard']['agree']:.1%}")
    print(f"  single-read rate {a['overall']['single_read']:.1%} — "
          f"direction {a['single_read_direction']}")
    print(f"  disagreement direction (primary->qa): "
          f"{a['disagreement_direction']}")
    print("  per-field agreement:")
    for f, r in sorted(a["per_field"].items(),
                       key=lambda kv: kv[1]["agree"] or 0):
        print(f"    {f:22} {r['agree']:.1%}  (n={r['n']}, "
              f"single-read {r['single_read']:.1%})")
    if "j2_concurrence" in a:
        print(f"  J2 reread concurrence: {a['j2_concurrence']}")
    for label in ("golden_1024", "golden_1536", "golden_adopted_1536"):
        if label in report and report[label]["j1_rows"]:
            g = report[label]
            print(f"\n{label}: n={g['j1_rows']} agree "
                  f"{g['overall']['agree']:.1%} · guard "
                  f"{g['guard']['agree'] if g['guard']['n'] else float('nan'):.1%} "
                  f"· warning agreement "
                  f"{(g['per_field'].get('government_warning') or {}).get('agree')}")


if __name__ == "__main__":
    main()
