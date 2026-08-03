"""Batch-physics generator: 4 batches x 300 golden applications for batch
upload load testing (queue arithmetic, shed rates, J1 backlog drain — the
AD-23/D5 numbers, measured instead of predicted).

Every item is deterministic (index-derived variation, no randomness): brand
names from word grids, beverage cycling, ABV spreads, and PLANTED
dispositions at known rates so a batch's expected outcome mix is known in
advance:
  - every 25th item: ABV outside tolerance        → expected MISMATCH
  - every 20th item: title-case warning heading   → expected MISMATCH
  - every 7th item:  a photographic degradation   → green or honest amber
  - every 5th item:  front+back pair              → multi-panel merge load
  - the rest: clean single-panel                  → expected all green

Output (GITIGNORED — ~25-30 MB per batch; regenerate on demand):
  api/eval/batches/batch{1..4}/
    *.jpg                  the label images
    manifest.csv           the UI batch-upload CSV (template columns)
    manifest.json          per-item ground truth + expected disposition

Run:  .venv/bin/python -m api.eval.generate_batches [--batches 4] [--per 300]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .generate_golden import WARNING_TEXT
from .generate_golden_cola import (back_panel, degrade_blur, degrade_dark,
                                   degrade_glare, degrade_skew, front_panel)

OUT = Path(__file__).parent / "batches"

ADJ = ["IRON", "SILVER", "COPPER", "GOLDEN", "STONE", "RIVER", "CEDAR",
       "HARBOR", "SUMMIT", "PRAIRIE", "FALCON", "JUNIPER", "GRANITE",
       "WILLOW", "BEACON"]
NOUN = ["RIDGE", "HOLLOW", "CREST", "MERIDIAN", "CANYON", "GROVE", "POINT",
        "VALE", "FORGE", "HARVEST", "SPRING", "SUMMIT", "COAST", "GLEN",
        "CROSSING"]

BEV = [
    ("wine", "wine", ["California Chardonnay — Table Wine", "Napa Valley Zinfandel",
                      "Oregon Pinot Noir", "Sonoma Cabernet Sauvignon"],
     [11.5, 12.5, 13.5, 14.8], "750 mL"),
    ("malt_beverage", "beer", ["American Pale Ale", "India Pale Ale",
                               "Amber Lager", "Oatmeal Stout"],
     [4.8, 5.2, 5.6, 6.4], "12 FL OZ"),
    ("distilled_spirits", "spirits", ["Straight Rye Whiskey",
                                      "Kentucky Straight Bourbon Whiskey",
                                      "Small Batch Gin", "Silver Rum"],
     [40.0, 45.0, 47.0, 50.0], "750 mL"),
]

DEGRADE = [("blur", degrade_blur), ("dark", degrade_dark),
           ("glare", degrade_glare), ("angle", lambda im: degrade_skew(im, 7))]


def item_spec(batch: int, i: int) -> tuple[dict, dict]:
    """(render_spec, manifest_entry-shape) for item i of a batch — pure
    function of (batch, i)."""
    n = batch * 1000 + i
    bev_type, kind, classes, abvs, net = BEV[i % 3]
    brand = f"{ADJ[n % 15]} {NOUN[(n // 15) % 15]}"
    class_type = classes[(n // 3) % 4]
    abv = abvs[(n // 12) % 4]
    if kind == "wine" and abv <= 14.0 and "Table" not in class_type:
        class_type = classes[0]                    # keep <=14% on the table-wine class
    abv_text = f"{abv}% ALC/VOL" if kind != "spirits" \
        else f"{abv:.0f}% Alc./Vol. ({int(abv * 2)} Proof)"

    trap_abv = (i % 25) == 24                      # printed ABV far from application
    trap_caps = (i % 20) == 19 and not trap_abv    # title-case heading
    degraded = DEGRADE[(i // 7) % 4] if (i % 7) == 6 and not (trap_abv or trap_caps) else None
    pair = (i % 5) == 4

    printed_abv = abv + (1.6 if trap_abv else 0.0)
    printed_abv_text = abv_text.replace(f"{abv}", f"{round(printed_abv, 1)}") \
        .replace(f"{int(abv * 2)}", f"{int(printed_abv * 2)}") if trap_abv else abv_text

    spec = dict(
        pipeline=kind, brand_label=brand, class_type=class_type,
        sulfites=(kind == "wine"), net_line=net,
        abv_line=printed_abv_text, front_abv=printed_abv_text, front_net=net,
        origin_line="", back_block=[f"BOTTLED BY {brand} CO."],
        warning_text=(WARNING_TEXT.replace("GOVERNMENT WARNING:",
                                           "Government Warning:")
                      if trap_caps else WARNING_TEXT),
        application=dict(beverage_type=bev_type, brand_name=brand,
                         class_type=class_type,
                         alcohol_content=f"{abv}%", net_contents=net),
    )
    if trap_abv:
        expect = "MISMATCH (printed ABV outside tolerance)"
    elif trap_caps:
        expect = "MISMATCH (title-case warning heading)"
    elif degraded:
        expect = f"green or honest amber ({degraded[0]} degradation)"
    else:
        expect = "all green"
    return spec, {"degrade": degraded, "pair": pair, "expect": expect}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=int, default=4)
    ap.add_argument("--per", type=int, default=300)
    args = ap.parse_args()

    for b in range(1, args.batches + 1):
        out = OUT / f"batch{b}"
        out.mkdir(parents=True, exist_ok=True)
        rows, manifest = [], []
        for i in range(args.per):
            spec, meta = item_spec(b, i)
            fid = f"b{b}_{i:03d}"
            front = front_panel(spec)
            if meta["degrade"]:
                front = meta["degrade"][1](front)
            front.save(out / f"{fid}.jpg", "JPEG", quality=80)
            back_name = ""
            files = [{"file": f"{fid}.jpg", "panel": "front"}]
            if meta["pair"]:
                back = back_panel(spec)
                if meta["degrade"]:
                    back = meta["degrade"][1](back)
                back_name = f"{fid}_back.jpg"
                back.save(out / back_name, "JPEG", quality=80)
                files.append({"file": back_name, "panel": "back"})
            app = spec["application"]
            rows.append([f"{fid}.jpg", app["beverage_type"], app["brand_name"],
                         app["class_type"], app["alcohol_content"],
                         app["net_contents"], back_name])
            manifest.append({"id": fid, "file": f"{fid}.jpg", "files": files,
                             "application": app, "expect": meta["expect"]})
        with open(out / "manifest.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["filename", "beverage_type", "brand_name", "class_type",
                        "alcohol_content", "net_contents", "back_filename"])
            w.writerows(rows)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
        n_traps = sum(1 for m in manifest if m["expect"].startswith("MISMATCH"))
        n_deg = sum(1 for m in manifest if "degradation" in m["expect"])
        n_pairs = sum(1 for m in manifest if len(m["files"]) == 2)
        print(f"batch{b}: {args.per} items — {n_traps} planted reds, "
              f"{n_deg} degraded, {n_pairs} front+back pairs")


if __name__ == "__main__":
    main()
