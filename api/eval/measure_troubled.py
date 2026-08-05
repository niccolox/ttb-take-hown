"""D-0 value gate for docs/plans/mm-ocr-augment.md (T1).

Measures, over the golden + COLA Cloud corpora, how many fields settle
troubled after the background layers — bucketed the way the mm second
read would actually see them (eng amendment 16):

- eligible_today   : NEEDS_REVIEW with an evidence bbox (J3's current set)
- eligible_widened : MISMATCH with an evidence bbox (amendment 17's set)
- unreachable      : troubled rows with NO bbox (no crop, no transcription)

Also models the J3_MAX_FIELDS=3 cap (fire counts + displaced rows) and
histograms reason codes per bucket so the "can a second reader even
help?" question is answered by data, not assertion.

Usage (server must be up — docker compose gpu or dev):
    .venv/bin/python api/eval/measure_troubled.py [--base http://localhost:8123]
Writes api/eval/results/d0-troubled-incidence.json and prints the
markdown table destined for the plan.
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "api" / "eval"

J3_MAX_FIELDS = 3
TROUBLED = ("MISMATCH", "NEEDS_REVIEW")

# reason codes a verbatim re-read could plausibly resolve (reading
# problems) vs ones it structurally cannot (crop/rule/absence problems)
TRANSCRIPTION_HELPABLE = {
    # a verbatim re-read adds signal on these: the text WAS located but the
    # reading of it is in doubt (or two engines disagree about it)
    "text_differs", "value_differs", "low_confidence", "unreadable",
    "ocr_confusable_punctuation", "partial_match", "value_out_of_tolerance",
    "engine_disagreement", "possible_ocr_misread", "statutory_text_differs",
    # NOT here (structurally un-helpable): weight_contrast_* (typography a
    # transcription cannot attest), format_nonstandard (rules issue on
    # already-read text), *_not_found / not_visible (no crop to read)
}


def corpora():
    m = json.load(open(EVAL / "golden" / "manifest.json"))
    items = []
    for it in m:
        t = it["truth"]
        app = {"beverage_type": t.get("beverage_type", "unspecified"),
               "brand_name": t.get("brand", ""),
               "class_type": t.get("class_type", ""),
               "alcohol_content": t.get("app_abv") or t.get("abv_line") or "",
               "net_contents": t.get("net_line", "")}
        items.append({"id": f"golden/{it['id']}", "application": app,
                      "paths": [EVAL / "golden" / it["file"]]})
    yield "golden", items

    for corpus in sorted((EVAL / "colacloud").iterdir()):
        mf = corpus / "manifest.json"
        if not mf.is_file():
            continue
        items = []
        for it in json.load(open(mf)):
            files = it.get("files") or [{"file": it["file"]}]
            paths = [corpus / f["file"] for f in files]
            items.append({"id": f"{corpus.name}/{it['id']}",
                          "application": it["application"],
                          "paths": [p for p in paths if p.is_file()]})
        yield f"colacloud/{corpus.name}", items


def post_verify(base: str, item: dict) -> dict | None:
    boundary = uuid.uuid4().hex
    body = io.BytesIO()

    def part(headers: str, payload: bytes):
        body.write(f"--{boundary}\r\n{headers}\r\n\r\n".encode())
        body.write(payload)
        body.write(b"\r\n")

    part('Content-Disposition: form-data; name="application"',
         json.dumps(item["application"]).encode())
    for p in item["paths"]:
        ctype = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        part(f'Content-Disposition: form-data; name="images"; '
             f'filename="{p.name}"\r\nContent-Type: {ctype}', p.read_bytes())
    body.write(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{base}/api/verify", data=body.getvalue(), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    for attempt in range(40):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = int(e.headers.get("Retry-After") or 3)
                time.sleep(min(wait, 15))
                continue
            print(f"  {item['id']}: HTTP {e.code} — skipped", file=sys.stderr)
            return None
        except (urllib.error.URLError, OSError) as e:
            print(f"  {item['id']}: {e} — retrying", file=sys.stderr)
            time.sleep(3)
    return None


def wait_settled(base: str, rid: str, budget_s: float = 120.0) -> dict | None:
    deadline = time.monotonic() + budget_s
    body = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/verify/{rid}",
                                        timeout=30) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError):
            time.sleep(2)
            continue
        if body.get("settled"):
            return body
        time.sleep(1.5)
    return body                       # unsettled after budget: measure as-is


def classify(fields: list[dict]) -> dict:
    rows = []
    for f in fields:
        status = f.get("status")
        if status not in TROUBLED:
            continue
        has_bbox = bool((f.get("evidence") or {}).get("bbox"))
        rows.append({"field": f.get("field"), "status": status,
                     "reason": f.get("reason_code") or "?",
                     "bbox": has_bbox})
    eligible_today = [r for r in rows if r["status"] == "NEEDS_REVIEW" and r["bbox"]]
    eligible_widened = [r for r in rows if r["status"] == "MISMATCH" and r["bbox"]]
    unreachable = [r for r in rows if not r["bbox"]]
    return {"troubled": rows,
            "eligible_today": eligible_today,
            "eligible_widened": eligible_widened,
            "unreachable": unreachable,
            "fire_today": min(J3_MAX_FIELDS, len(eligible_today)),
            "fire_widened": min(J3_MAX_FIELDS,
                                len(eligible_today) + len(eligible_widened)),
            "displaced": max(0, len(eligible_today) + len(eligible_widened)
                             - J3_MAX_FIELDS)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8123")
    args = ap.parse_args()

    per_corpus, details = {}, []
    for corpus, items in corpora():
        agg = {"apps": 0, "apps_with_troubled": 0, "fields": 0,
               "troubled": 0, "eligible_today": 0, "eligible_widened": 0,
               "unreachable": 0, "fire_today": 0, "fire_widened": 0,
               "displaced": 0,
               "reasons_today": Counter(), "reasons_widened": Counter(),
               "reasons_unreachable": Counter()}
        for item in items:
            if not item["paths"]:
                continue
            first = post_verify(args.base, item)
            if first is None:
                continue
            body = wait_settled(args.base, first["result_id"]) or first
            fields = body.get("fields") or []
            c = classify(fields)
            agg["apps"] += 1
            agg["fields"] += len(fields)
            agg["troubled"] += len(c["troubled"])
            agg["apps_with_troubled"] += bool(c["troubled"])
            for k in ("eligible_today", "eligible_widened", "unreachable"):
                agg[k] += len(c[k])
                agg[f"reasons_{k.split('_')[-1]}"].update(
                    r["reason"] for r in c[k])
            for k in ("fire_today", "fire_widened", "displaced"):
                agg[k] += c[k]
            details.append({"id": item["id"], "settled": body.get("settled"),
                            **{k: c[k] for k in
                               ("troubled", "fire_today", "fire_widened")}})
            print(f"{item['id']}: {len(c['troubled'])} troubled "
                  f"(today {len(c['eligible_today'])}, widened +"
                  f"{len(c['eligible_widened'])}, unreachable "
                  f"{len(c['unreachable'])})")
        for k in ("reasons_today", "reasons_widened", "reasons_unreachable"):
            agg[k] = dict(agg[k].most_common())
        per_corpus[corpus] = agg

    total = Counter()
    reasons = {"today": Counter(), "widened": Counter(), "unreachable": Counter()}
    for agg in per_corpus.values():
        for k, v in agg.items():
            if isinstance(v, int):
                total[k] += v
            elif k.startswith("reasons_"):
                reasons[k.split("_")[1]].update(v)

    helpable = {b: sum(n for r, n in cnt.items() if r in TRANSCRIPTION_HELPABLE)
                for b, cnt in reasons.items()}

    out = {"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "j3_max_fields": J3_MAX_FIELDS,
           "per_corpus": per_corpus, "totals": dict(total),
           "reasons": {k: dict(v.most_common()) for k, v in reasons.items()},
           "transcription_helpable": helpable, "apps": details}
    results = EVAL / "results" / "d0-troubled-incidence.json"
    results.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {results}")

    t = total
    print("\n| Corpus | Apps | Troubled fields | Eligible today (NR∧bbox) | "
          "Widened (MM∧bbox) | Unreachable (no bbox) | Fire/app today→widened |")
    print("|---|---|---|---|---|---|---|")
    for name, a in per_corpus.items():
        n = max(1, a["apps"])
        print(f"| {name} | {a['apps']} | {a['troubled']} | "
              f"{a['eligible_today']} | {a['eligible_widened']} | "
              f"{a['unreachable']} | {a['fire_today']/n:.2f}→"
              f"{a['fire_widened']/n:.2f} |")
    n = max(1, t["apps"])
    print(f"| **TOTAL** | {t['apps']} | {t['troubled']} | "
          f"{t['eligible_today']} | {t['eligible_widened']} | "
          f"{t['unreachable']} | {t['fire_today']/n:.2f}→"
          f"{t['fire_widened']/n:.2f} |")
    print(f"\nreason codes (today): {dict(reasons['today'].most_common(8))}")
    print(f"reason codes (widened): {dict(reasons['widened'].most_common(8))}")
    print(f"reason codes (unreachable): {dict(reasons['unreachable'].most_common(8))}")
    print(f"transcription-helpable counts: {helpable} "
          f"(of today {t['eligible_today']} / widened {t['eligible_widened']})")
    print(f"cap displacement total: {t['displaced']}")


if __name__ == "__main__":
    main()
