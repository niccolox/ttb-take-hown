"""Real-label eval: run the full pipeline over the Napa corpus (api/eval/napa).

Unlike the synthetic golden set (known-exact ground truth), these are real
photographs of real Napa/California wines with human-transcribed truth and
*expected-behavior notes* — the run is exploratory: it reports what the
pipeline concluded next to what a human expects, plus latency. Results are
committed as benchmark artifacts.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

NAPA = Path(__file__).parent / "napa"
RESULTS = Path(__file__).parent / "results"


def main():
    import numpy as np
    from PIL import Image

    import sys
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from api.extractor import PaddleExtractor
    from api.verify import verify

    manifest = json.loads((NAPA / "manifest.json").read_text())
    ex = PaddleExtractor()
    t0 = time.perf_counter()
    ex.warm(str(NAPA / manifest[0]["file"]))
    warm_s = time.perf_counter() - t0

    rows, lat = [], []
    for case in manifest:
        path = NAPA / case["file"]
        img = Image.open(path).convert("RGB")
        if max(img.size) > 2000:                       # same downscale as the API path
            r = 2000 / max(img.size)
            img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        tmp = str(RESULTS / "_tmp_napa.jpg")
        img.save(tmp, "JPEG", quality=92)
        t0 = time.perf_counter()
        words = ex.extract(tmp)
        result = verify(words, case["application"],
                        image_gray=np.array(img.convert("L")))
        dt = time.perf_counter() - t0
        lat.append(dt)
        fields = {f["field"]: {"status": f["status"], "label_value": f["label_value"],
                               "note": f["note"][:90]} for f in result["fields"]}
        rows.append({"id": case["id"], "latency_s": round(dt, 2),
                     "screening": result["screening_result"],
                     "fields": fields, "expect": case["expect"]})
        print(f"\n=== {case['id']}  ({dt:.2f}s)  → {result['screening_result']}")
        for name, f in fields.items():
            lv = (f["label_value"] or "")[:40]
            print(f"   {name:22s} {f['status']:18s} {lv:40s} | {f['note'][:60]}")
        print(f"   EXPECTED: {case['expect'][:100]}")

    Path(tmp).unlink(missing_ok=True)
    summary = {
        "corpus": "napa (8 real Napa/California wine label photos, Wikimedia Commons, CC)",
        "engine": "PaddleOCR PP-OCRv5 (pinned)",
        "warmup_s": round(warm_s, 2),
        "latency_p50_s": round(statistics.median(sorted(lat)), 2),
        "latency_max_s": round(max(lat), 2),
    }
    (RESULTS / "napa-real-labels.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
