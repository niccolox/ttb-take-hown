"""COLA Cloud → eval-batch pipeline.

Pulls real, approved TTB label records (via the COLA Cloud API — the commercial
front-end over the public COLA Registry) for wine / beer / spirits and writes
eval corpora in this repo's manifest format, with the *registry record itself*
as application ground truth: brand_name, class_name, ABV, and net contents come
from the approved COLA, and the image is the actual approved label artwork.

Usage:
    export COLACLOUD_API_KEY=...        # from https://app.colacloud.us dashboard
    .venv/bin/python api/eval/colacloud_pipeline.py --per-type 4
    .venv/bin/python api/eval/colacloud_pipeline.py --types wine --per-type 8 \
        --query "napa" --from-date 2005-01-01

Quota notes (docs.colacloud.us): each detail fetch counts against the monthly
detail-view quota (free tier: 200/mo, 10 req/min burst). The pipeline sleeps
between detail calls and prints remaining quota from the response headers.
Output: api/eval/colacloud/{wine|beer|spirits}/ + manifest.json per type,
auto-registered as UI eval sets by api/main.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

OUT_BASE = Path(__file__).parent / "colacloud"

TYPES = {  # our name -> API product_type / our beverage_type enum
    "wine": ("wine", "wine"),
    "beer": ("malt beverage", "malt_beverage"),
    "spirits": ("distilled spirits", "distilled_spirits"),
}

UNIT_LABEL = {"milliliters": "mL", "liters": "L", "fluid ounces": "FL OZ",
              "gallons": "GAL", "pints": "PT", "quarts": "QT",
              "beer barrels": "BBL"}


def net_contents_str(volume, volume_unit) -> str:
    if volume is None or not volume_unit:
        return ""
    unit = UNIT_LABEL.get(str(volume_unit).lower(), str(volume_unit))
    v = int(volume) if float(volume).is_integer() else volume
    return f"{v} {unit}"


def build_entry(detail: dict, bev_type: str, image_file: str) -> dict:
    """Pure manifest-entry builder (unit-tested without network)."""
    abv = detail.get("abv")
    app = {
        "beverage_type": bev_type,
        "brand_name": detail.get("brand_name") or "",
        "class_type": detail.get("class_name") or "",
        "alcohol_content": f"{abv}%" if abv is not None else "",
        "net_contents": net_contents_str(detail.get("volume"), detail.get("volume_unit")),
    }
    return {
        "id": detail["ttb_id"],
        "file": image_file,
        "application": app,
        "note": (f"Approved COLA {detail['ttb_id']} ({detail.get('approval_date', '?')}); "
                 f"registry record is ground truth — verdicts should be matches or honest "
                 f"reviews, never false mismatches. Product: "
                 f"{(detail.get('product_name') or detail.get('brand_name') or '')[:60]}"),
        "provenance": {
            "ttb_id": detail["ttb_id"],
            "approval_date": detail.get("approval_date"),
            "permit_number": detail.get("permit_number"),
            "origin": detail.get("origin_name"),
            "source": "TTB Public COLA Registry via COLA Cloud API (public record); "
                      "label artwork is part of the public approval record",
        },
    }


def pick_image(detail: dict) -> tuple[str | None, str]:
    """Prefer the front label ('brand' container position), else main image."""
    for img in detail.get("images") or []:
        pos = (img.get("container_position") or "").lower()
        if img.get("image_url") and pos in ("front", "brand", "brand (front)"):
            return img["image_url"], pos or "front"
    if detail.get("main_image_url"):
        return detail["main_image_url"], "main"
    for img in detail.get("images") or []:
        if img.get("image_url"):
            return img["image_url"], img.get("container_position") or "unknown"
    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--types", default="wine,beer,spirits",
                    help="comma list from: wine,beer,spirits")
    ap.add_argument("--per-type", type=int, default=4)
    ap.add_argument("--query", default=None, help="optional full-text filter (e.g. 'napa')")
    ap.add_argument("--from-date", default=None,
                    help="approval_date_from YYYY-MM-DD (default: API's last-365-days window)")
    ap.add_argument("--sleep", type=float, default=6.5,
                    help="seconds between detail calls (free-tier burst is 10/min)")
    args = ap.parse_args()

    key = os.environ.get("COLACLOUD_API_KEY")
    if not key:
        print("COLACLOUD_API_KEY is not set.\n"
              "Get a key from https://app.colacloud.us (free tier: 200 detail views/mo),\n"
              "then:  export COLACLOUD_API_KEY=...  and re-run.", file=sys.stderr)
        return 1

    import httpx
    from colacloud import ColaCloud

    wanted = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = set(wanted) - set(TYPES)
    if unknown:
        print(f"Unknown types: {sorted(unknown)} (choose from {list(TYPES)})", file=sys.stderr)
        return 1

    client = ColaCloud(api_key=key)
    totals = {}
    try:
        for tname in wanted:
            api_type, bev = TYPES[tname]
            out_dir = OUT_BASE / tname
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n=== {tname} (product_type={api_type!r}) ===")

            resp = client.colas.list(
                product_type=api_type, q=args.query,
                approval_date_from=args.from_date,
                per_page=min(50, args.per_type * 5),
            )
            candidates = [s for s in resp.data if (s.image_count or 0) > 0]
            print(f"search: {len(resp.data)} records, {len(candidates)} with images")

            manifest, taken = [], 0
            for summary in candidates:
                if taken >= args.per_type:
                    break
                detail = client.colas.get(summary.ttb_id)
                d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
                url, pos = pick_image(d)
                if not url:
                    print(f"  skip {summary.ttb_id}: no usable image url")
                    time.sleep(args.sleep)
                    continue
                ext = ".jpg" if ".png" not in url.lower() else ".png"
                fname = f"{summary.ttb_id}{ext}"
                img = httpx.get(url, timeout=60, follow_redirects=True)
                img.raise_for_status()
                (out_dir / fname).write_bytes(img.content)
                entry = build_entry(d, bev, fname)
                entry["provenance"]["image_panel"] = pos
                manifest.append(entry)
                taken += 1
                q = client.quota_info()
                remaining = getattr(q, "detail_views_remaining", None) if q else None
                print(f"  + {summary.ttb_id}  {d.get('brand_name','')!r:35.35} "
                      f"abv={d.get('abv')} vol={net_contents_str(d.get('volume'), d.get('volume_unit'))} "
                      f"panel={pos}  [{len(img.content)//1024}KB]"
                      + (f"  quota_left={remaining}" if remaining is not None else ""))
                time.sleep(args.sleep)

            (out_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False))
            totals[tname] = len(manifest)
            print(f"wrote {len(manifest)} entries → {out_dir}/manifest.json")
    finally:
        client.close()

    print(f"\nDone: {totals}. The UI auto-registers these as eval sets "
          f"(restart the server / refresh the page).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
