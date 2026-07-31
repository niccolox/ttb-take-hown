"""M0 feasibility spike (PLAN.md M0): measure OCR fidelity + latency on the golden set.

Proves or breaks the riskiest premise — OCR fidelity on stylized label typography
and the 5s budget on THIS machine — before any UI work. Outputs JSON + markdown.

Metrics per label:
  - per-field located? (targeted fuzzy search of ground-truth value in OCR text)
  - warning: caps-prefix present case-sensitively in RAW OCR text (the trap check)
  - warning: statutory-text token coverage
  - latency (model-warm, per image)
Aggregates: field-location rate, warning caps-trap discrimination, exact-text rate
on clean images, p50/p95 latency.
"""

from __future__ import annotations

import json
import re
import statistics
import time
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz

GOLDEN = Path(__file__).parent / "golden"
RESULTS = Path(__file__).parent / "results"

WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


def located(expected: str, ocr_text: str, threshold: int = 80) -> tuple[bool, float]:
    """Targeted verification: fuzzy-search expected value in OCR text."""
    if not expected:
        return False, 0.0
    score = fuzz.partial_ratio(normalize(expected), normalize(ocr_text))
    return score >= threshold, score


def main():
    from paddleocr import PaddleOCR

    RESULTS.mkdir(exist_ok=True)
    manifest = json.loads((GOLDEN / "manifest.json").read_text())

    t0 = time.perf_counter()
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=True, lang="en")
    init_s = time.perf_counter() - t0

    # warmup (model load / first-inference JIT) — mirrors the plan's boot warmup
    warm = GOLDEN / manifest[0]["file"]
    t0 = time.perf_counter()
    ocr.predict(str(warm))
    warmup_s = time.perf_counter() - t0

    rows, latencies = [], []
    for case in manifest:
        path = GOLDEN / case["file"]
        t0 = time.perf_counter()
        out = ocr.predict(str(path))
        dt = time.perf_counter() - t0
        latencies.append(dt)

        texts: list[str] = []
        for page in out:
            texts.extend(page.get("rec_texts", []) if isinstance(page, dict) else page["rec_texts"])
        raw = " ".join(texts)

        truth = case.get("truth", {})
        fields = {}
        for key in ("brand", "class_type", "abv_line", "net_line"):
            val = truth.get(key)
            if val:
                ok, score = located(val, raw)
                fields[key] = {"located": ok, "score": round(score, 1)}

        caps_prefix_raw = bool(re.search(r"GOVERNMENT\s+WARNING\s*:?", raw))          # caps as printed
        title_prefix_raw = bool(re.search(r"Government\s+Warning", raw))               # title-case as printed
        warn_cov = fuzz.token_set_ratio(normalize(WARNING_TEXT), normalize(raw))

        rows.append({
            "id": case["id"], "degrade": case["degrade"], "latency_s": round(dt, 2),
            "fields": fields,
            "warning": {"caps_prefix_in_raw": caps_prefix_raw,
                        "titlecase_prefix_in_raw": title_prefix_raw,
                        "token_coverage": round(warn_cov, 1)},
            "expect": case["expect"],
            "n_text_blocks": len(texts),
        })
        print(f"{case['id']:32s} {dt:5.2f}s blocks={len(texts):3d} "
              f"caps_raw={caps_prefix_raw} title_raw={title_prefix_raw} cov={warn_cov:5.1f}")

    lat_sorted = sorted(latencies)
    summary = {
        "machine": "16-core CPU (dev box), paddle CPU wheel",
        "engine": "PaddleOCR (PP-OCR v5 default pipeline, textline orientation on)",
        "init_s": round(init_s, 2), "warmup_first_infer_s": round(warmup_s, 2),
        "n_labels": len(rows),
        "latency_p50_s": round(statistics.median(lat_sorted), 2),
        "latency_p95_s": round(lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)], 2),
        "latency_max_s": round(lat_sorted[-1], 2),
        "field_location_rate": round(
            sum(f["located"] for r in rows for f in r["fields"].values())
            / max(1, sum(len(r["fields"]) for r in rows)), 3),
    }
    # caps-trap discrimination: clean spirits label should show caps_raw AND the
    # title-case trap should show title_raw (and ideally NOT caps_raw)
    clean = next(r for r in rows if r["id"] == "spirits_clean")
    trap = next(r for r in rows if r["id"] == "trap_titlecase_warning")
    summary["caps_trap_discriminated"] = bool(
        clean["warning"]["caps_prefix_in_raw"] and trap["warning"]["titlecase_prefix_in_raw"]
        and not trap["warning"]["caps_prefix_in_raw"])

    out = {"summary": summary, "rows": rows}
    (RESULTS / "m0-paddleocr.json").write_text(json.dumps(out, indent=2))
    print("\n=== M0 SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
