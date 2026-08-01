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
import logging
import logging.handlers
import os
import re
import sys
import time
from pathlib import Path

OUT_BASE = Path(__file__).parent / "colacloud"

log = logging.getLogger("colacloud")


def setup_logging() -> Path:
    """Debug log → api/eval/colacloud/pipeline.log (rotating, survives in the
    docker-dev bind mount) AND stdout (visible in `docker compose logs -f` /
    the dev console). Idempotent."""
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    logfile = OUT_BASE / "pipeline.log"
    if not log.handlers:
        log.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s [colacloud] %(message)s")
        fh = logging.handlers.RotatingFileHandler(logfile, maxBytes=1_000_000,
                                                  backupCount=2)
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        sh.setLevel(logging.INFO)
        log.addHandler(fh)
        log.addHandler(sh)
    return logfile

TYPES = {  # our name -> API product_type / our beverage_type enum
    "wine": ("wine", "wine"),
    "beer": ("malt beverage", "malt_beverage"),
    "spirits": ("distilled spirits", "distilled_spirits"),
    "imported_wine": ("wine", "wine"),
    "champagne": ("wine", "wine"),
}

# extra search filters per pipeline (passed to colas.list)
TYPE_FILTERS = {
    "imported_wine": {"domestic_or_imported": "imported"},
    "champagne": {"domestic_or_imported": "imported"},
}

# default full-text query per pipeline (used when the caller passes none)
TYPE_DEFAULT_QUERY = {
    "champagne": "champagne",
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


def registry_block(detail: dict) -> dict:
    """The COLA Detail record, mirroring the TTB printable view (status, class/
    type, origin, fanciful name, dates, varietals...). The applicant-assigned
    serial #, vendor code, and formula shown on TTB's printable view are not
    exposed by the COLA Cloud API — never derived (the serial is NOT part of
    the TTB ID). None/empty fields are omitted."""
    fields = {
        "status": detail.get("application_status"),
        "type_of_application": detail.get("application_type"),
        "class_type_code": detail.get("class_name"),
        "class_id": detail.get("class_id"),
        "origin": detail.get("origin_name"),
        "origin_id": detail.get("origin_id"),
        "brand_name": detail.get("brand_name"),
        "fanciful_name": detail.get("product_name"),
        "domestic_or_imported": detail.get("domestic_or_imported"),
        "grape_varietals": detail.get("grape_varietals"),
        "wine_vintage_year": detail.get("wine_vintage_year"),
        "wine_appellation": detail.get("wine_appellation"),
        "total_bottle_capacity": detail.get("for_distinctive_capacity"),
        "is_distinctive_container": detail.get("is_distinctive_container"),
        "application_date": detail.get("application_date"),
        "approval_date": detail.get("approval_date"),
        "expiration_date": detail.get("expiration_date"),
        "permit_number": detail.get("permit_number"),
    }
    return {k: v for k, v in fields.items() if v not in (None, "", [], "N/A")}


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
        "registry": registry_block(detail),
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


def pick_panels(detail: dict) -> list[tuple[str, str]]:
    """Front AND back panels [(url, panel)] — the warning usually lives on the
    back label, so multi-panel is the honest input. Falls back to pick_image."""
    panels: list[tuple[str, str]] = []
    seen: set[str] = set()
    for want in (("front", "brand", "brand (front)", "main"), ("back", "back (rear)")):
        for img in detail.get("images") or []:
            pos = (img.get("container_position") or "").lower()
            url = img.get("image_url")
            if url and url not in seen and pos in want:
                panels.append((url, "front" if want[0] == "front" else "back"))
                seen.add(url)
                break
    if not panels:
        url, pos = pick_image(detail)
        if url:
            panels.append((url, pos or "front"))
    return panels


def _load_manifest(out_dir: Path) -> list[dict]:
    p = out_dir / "manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return []
    return []


def _save_manifest(out_dir: Path, manifest: list[dict]) -> None:
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str))  # SDK dates


def _with_rate_limit(fn, *, progress, attempts: int = 4):
    """Run an API call; on 429, honor Retry-After and retry (burst is 10/min)."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if "429" not in msg and "Too many requests" not in msg:
                raise
            wait = 65
            import re as _re
            if m := _re.search(r"retry after (\d+)", msg):
                wait = int(m.group(1)) + 5
            if i == attempts - 1:
                log.error("rate limit: giving up after %d attempts: %s", attempts, msg[:200])
                raise
            log.warning("rate limit hit — waiting %ss (attempt %d/%d)", wait, i + 1, attempts)
            progress(f"rate-limited — waiting {wait}s (attempt {i + 1}/{attempts})")
            time.sleep(wait)


def pull_type(tname: str, *, api_key: str, per_type: int = 4, query: str | None = None,
              from_date: str | None = None, sleep: float = 7.0,
              progress=lambda msg: None) -> int:
    """Pull one commodity batch. Returns TOTAL entries in the manifest.

    Crash-safe: the manifest is written incrementally after every successful
    entry, and retries merge (dedupe by TTB ID) — a rate-limited or interrupted
    pull keeps everything it already fetched, and the UI sees a valid set.
    """
    import httpx
    from colacloud import ColaCloud

    setup_logging()
    api_type, bev = TYPES[tname]
    out_dir = OUT_BASE / tname
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out_dir)
    have = {m["id"] for m in manifest}
    query = query or TYPE_DEFAULT_QUERY.get(tname)
    log.info("pull_type start: type=%s per_type=%s query=%r from_date=%r existing=%d",
             tname, per_type, query, from_date, len(have))

    client = ColaCloud(api_key=api_key)
    try:
        progress(f"searching {api_type} records…")
        extra = TYPE_FILTERS.get(tname, {})
        # Prefer records with 2+ images (front AND back panels — image_count is
        # free in search results, so this costs no detail views). If a page has
        # no multi-panel candidates (common for beer: cans are one wraparound
        # artwork), search a few pages deeper before settling for single-image
        # fill — list calls don't spend detail-view quota.
        fresh, multi, returned = [], [], 0
        for page in range(1, 5):
            resp = _with_rate_limit(
                lambda page=page: client.colas.list(product_type=api_type, q=query,
                                                    approval_date_from=from_date,
                                                    per_page=min(50, max(20, per_type * 5)),
                                                    page=page, **extra),
                progress=progress)
            returned += len(resp.data)
            page_fresh = [s for s in resp.data
                          if (s.image_count or 0) > 0 and s.ttb_id not in have]
            fresh.extend(page_fresh)
            multi.extend(s for s in page_fresh if (s.image_count or 0) >= 2)
            if len(multi) >= per_type or not resp.data:
                break
            progress(f"page {page}: {len(multi)} front+back so far — searching deeper…")
        candidates = multi + [s for s in fresh if (s.image_count or 0) == 1]
        log.info("search: %d records returned, %d new with images (%d front+back)",
                 returned, len(fresh), len(multi))
        log.debug("candidate ttb_ids: %s", [s.ttb_id for s in candidates[:20]])
        progress(f"{len(fresh)} new candidates ({len(multi)} with front+back); "
                 f"pulling up to {per_type}")

        taken = 0
        for summary in candidates:
            if taken >= per_type:
                break
            detail = _with_rate_limit(lambda s=summary: client.colas.get(s.ttb_id),
                                      progress=progress)
            d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            panels = pick_panels(d)
            if not panels:
                time.sleep(sleep)
                continue
            files = []
            for url, pos in panels:
                ext = ".jpg" if ".png" not in url.lower() else ".png"
                fname = f"{summary.ttb_id}_{pos}{ext}"
                img = httpx.get(url, timeout=60, follow_redirects=True)
                img.raise_for_status()
                (out_dir / fname).write_bytes(img.content)
                files.append({"file": fname, "panel": pos})
            entry = build_entry(d, bev, files[0]["file"])
            entry["files"] = files                       # all panels (front first)
            entry["provenance"]["image_panel"] = ",".join(p for _, p in panels)
            if tname in ("imported_wine", "champagne"):
                entry["note"] += (" IMPORTED: country of origin is mandatory on the label "
                                  f"(origin: {d.get('origin_name', '?')}).")
            if tname == "champagne":
                entry["note"] += (" CHAMPAGNE: protected appellation — class/type and "
                                  "origin must agree (French sparkling only).")
            manifest.append(entry)
            _save_manifest(out_dir, manifest)        # incremental — crash-safe
            taken += 1
            q = getattr(client, "quota_info", None)
            if callable(q):                          # SDK exposes this as property OR method
                q = q()
            log.info("fetched %s brand=%r abv=%s vol=%s panels=%s img=%dKB quota_left=%s",
                     summary.ttb_id, d.get("brand_name"), d.get("abv"),
                     net_contents_str(d.get("volume"), d.get("volume_unit")),
                     ",".join(f["panel"] for f in files),
                     sum((out_dir / f["file"]).stat().st_size for f in files) // 1024,
                     getattr(q, "detail_views_remaining", "?") if q else "?")
            progress(f"{taken}/{per_type}: {d.get('brand_name','')[:40]}")
            time.sleep(sleep)

        _save_manifest(out_dir, manifest)
        log.info("pull_type done: type=%s new=%d manifest_total=%d", tname, taken, len(manifest))
        return len(manifest)
    except Exception:
        log.exception("pull_type failed: type=%s", tname)
        raise
    finally:
        client.close()


def recover_orphans(tname: str, *, api_key: str, sleep: float = 8.0,
                    progress=lambda msg: None) -> int:
    """Build manifest entries for images already on disk but missing from the
    manifest (e.g. a pull that died before writing). Costs one detail view per
    orphan."""
    from colacloud import ColaCloud

    setup_logging()
    _, bev = TYPES[tname]
    out_dir = OUT_BASE / tname
    if not out_dir.exists():
        return 0
    manifest = _load_manifest(out_dir)
    have = {m["id"] for m in manifest}
    # A file is an orphan only if NO manifest entry references it. Panel files
    # are named {ttb_id}_{panel}.ext — the stem is NOT the TTB ID, so strip the
    # panel suffix to key the detail lookup, and group panels of the same COLA
    # into one recovered entry (one detail view per COLA, not per file).
    referenced = {m["file"] for m in manifest}
    for m in manifest:
        referenced.update(f_["file"] for f_ in m.get("files") or [])
    by_id: dict[str, list[Path]] = {}
    for p in sorted(out_dir.glob("*.jpg")) + sorted(out_dir.glob("*.png")):
        if p.name in referenced:
            continue
        ttb_id = re.sub(r"_(front|back|main|unknown)$", "", p.stem)
        if ttb_id in have:          # entry exists; stray panel file, not an orphan
            continue
        by_id.setdefault(ttb_id, []).append(p)
    log.info("recover_orphans: type=%s manifest=%d orphans=%d (files=%d)",
             tname, len(have), len(by_id), sum(len(v) for v in by_id.values()))
    if not by_id:
        return len(manifest)

    client = ColaCloud(api_key=api_key)
    try:
        for ttb_id, paths in by_id.items():
            try:
                detail = _with_rate_limit(lambda t=ttb_id: client.colas.get(t),
                                          progress=progress)
            except Exception as exc:
                if "404" in str(exc):   # not a real COLA id — skip, don't kill the run
                    log.warning("recover_orphans: %s not found in registry — skipped", ttb_id)
                    progress(f"skipped {ttb_id}: not found in registry")
                    time.sleep(sleep)
                    continue
                raise
            d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            # front first so entry["file"] (the UI's primary image) is the front
            panel_of = lambda p: (re.search(r"_(front|back|main|unknown)$", p.stem)
                                  or [None, "front"])[1]
            paths.sort(key=lambda p: 0 if panel_of(p) in ("front", "main") else 1)
            entry = build_entry(d, bev, paths[0].name)
            entry["files"] = [{"file": p.name, "panel": panel_of(p)} for p in paths]
            entry["provenance"]["image_panel"] = "recovered"
            manifest.append(entry)
            _save_manifest(out_dir, manifest)
            log.info("recovered %s panels=%s brand=%r", ttb_id,
                     [p.name for p in paths], d.get("brand_name"))
            progress(f"recovered {ttb_id}: {d.get('brand_name','')[:40]}")
            time.sleep(sleep)
        return len(manifest)
    except Exception:
        log.exception("recover_orphans failed: type=%s", tname)
        raise
    finally:
        client.close()


def backfill_panels(tname: str, *, api_key: str, sleep: float = 8.0,
                    progress=lambda msg: None) -> int:
    """Add missing back panels to entries pulled before multi-panel support.
    Costs one detail view per entry that lacks a `files` list. Idempotent."""
    import httpx
    from colacloud import ColaCloud

    setup_logging()
    out_dir = OUT_BASE / tname
    if not out_dir.exists():
        return 0
    manifest = _load_manifest(out_dir)
    todo = [m for m in manifest if not m.get("files")]
    log.info("backfill_panels: type=%s entries=%d todo=%d", tname, len(manifest), len(todo))
    if not todo:
        return 0

    client = ColaCloud(api_key=api_key)
    done = 0
    try:
        for m in todo:
            detail = _with_rate_limit(lambda m=m: client.colas.get(m["id"]),
                                      progress=progress)
            d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            panels = pick_panels(d)
            files = []
            for url, pos in panels:
                ext = ".jpg" if ".png" not in url.lower() else ".png"
                fname = f"{m['id']}_{pos}{ext}"
                if not (out_dir / fname).exists():
                    img = httpx.get(url, timeout=60, follow_redirects=True)
                    img.raise_for_status()
                    (out_dir / fname).write_bytes(img.content)
                files.append({"file": fname, "panel": pos})
            if files:
                m["file"] = files[0]["file"]
                m["files"] = files
                m["provenance"]["image_panel"] = ",".join(p for _, p in panels)
            _save_manifest(out_dir, manifest)
            done += 1
            log.info("backfilled %s panels=%s", m["id"], [f["file"] for f in files])
            progress(f"backfilled {m['id']}: {len(files)} panel(s)")
            time.sleep(sleep)
        return done
    except Exception:
        log.exception("backfill_panels failed: type=%s", tname)
        raise
    finally:
        client.close()


def pull_by_id(tname: str, ttb_ids: list[str], *, api_key: str, sleep: float = 7.0,
               progress=lambda msg: None) -> int:
    """Pull specific COLAs by TTB ID into a type's corpus (front+back panels,
    registry block). One detail view per ID; skips IDs already in the manifest."""
    import httpx
    from colacloud import ColaCloud

    setup_logging()
    _, bev = TYPES[tname]
    out_dir = OUT_BASE / tname
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(out_dir)
    have = {m["id"] for m in manifest}
    todo = [t for t in ttb_ids if t not in have]
    log.info("pull_by_id: type=%s ids=%d todo=%d", tname, len(ttb_ids), len(todo))

    client = ColaCloud(api_key=api_key)
    added = 0
    try:
        for ttb_id in todo:
            detail = _with_rate_limit(lambda t=ttb_id: client.colas.get(t),
                                      progress=progress)
            d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            panels = pick_panels(d)
            if not panels:
                log.warning("pull_by_id: %s has no images — skipped", ttb_id)
                progress(f"skipped {ttb_id}: no images")
                time.sleep(sleep)
                continue
            files = []
            for url, pos in panels:
                ext = ".jpg" if ".png" not in url.lower() else ".png"
                fname = f"{ttb_id}_{pos}{ext}"
                img = httpx.get(url, timeout=60, follow_redirects=True)
                img.raise_for_status()
                (out_dir / fname).write_bytes(img.content)
                files.append({"file": fname, "panel": pos})
            entry = build_entry(d, bev, files[0]["file"])
            entry["files"] = files
            entry["provenance"]["image_panel"] = ",".join(p for _, p in panels)
            manifest.append(entry)
            _save_manifest(out_dir, manifest)
            added += 1
            log.info("pull_by_id fetched %s brand=%r panels=%d", ttb_id,
                     d.get("brand_name"), len(files))
            progress(f"fetched {ttb_id}: {(d.get('brand_name') or '')[:40]}")
            time.sleep(sleep)
        return added
    except Exception:
        log.exception("pull_by_id failed: type=%s", tname)
        raise
    finally:
        client.close()


def backfill_registry(tname: str, *, api_key: str, sleep: float = 8.0,
                      progress=lambda msg: None) -> int:
    """Add the COLA Detail registry block to entries pulled before it existed.
    Costs one detail view per entry lacking `registry`. Idempotent."""
    from colacloud import ColaCloud

    setup_logging()
    out_dir = OUT_BASE / tname
    if not out_dir.exists():
        return 0
    manifest = _load_manifest(out_dir)
    todo = [m for m in manifest if not m.get("registry")]
    log.info("backfill_registry: type=%s entries=%d todo=%d", tname, len(manifest), len(todo))
    if not todo:
        return 0

    client = ColaCloud(api_key=api_key)
    done = 0
    try:
        for m in todo:
            detail = _with_rate_limit(lambda m=m: client.colas.get(m["id"]),
                                      progress=progress)
            d = detail.model_dump() if hasattr(detail, "model_dump") else dict(detail)
            m["registry"] = registry_block(d)
            _save_manifest(out_dir, manifest)
            done += 1
            log.info("registry backfilled %s fields=%d", m["id"], len(m["registry"]))
            progress(f"registry {m['id']}: {len(m['registry'])} fields")
            time.sleep(sleep)
        return done
    except Exception:
        log.exception("backfill_registry failed: type=%s", tname)
        raise
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--types", default="wine,beer,spirits",
                    help="comma list from: wine,beer,spirits,imported_wine,champagne")
    ap.add_argument("--per-type", type=int, default=4)
    ap.add_argument("--query", default=None, help="optional full-text filter (e.g. 'napa')")
    ap.add_argument("--from-date", default=None,
                    help="approval_date_from YYYY-MM-DD (default: API's last-365-days window)")
    ap.add_argument("--sleep", type=float, default=6.5,
                    help="seconds between detail calls (free-tier burst is 10/min)")
    ap.add_argument("--backfill-panels", action="store_true",
                    help="add missing back panels to already-pulled corpora, then exit")
    ap.add_argument("--ttb-id", action="append", default=[],
                    help="pull specific TTB ID(s) into the (single) --types corpus, then exit")
    ap.add_argument("--backfill-registry", action="store_true",
                    help="add the COLA Detail registry block to already-pulled corpora, then exit")
    args = ap.parse_args()

    key = os.environ.get("COLACLOUD_API_KEY")
    if not key:
        print("COLACLOUD_API_KEY is not set.\n"
              "Get a key from https://app.colacloud.us (free tier: 200 detail views/mo),\n"
              "then:  export COLACLOUD_API_KEY=...  and re-run.", file=sys.stderr)
        return 1

    wanted = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = set(wanted) - set(TYPES)
    if unknown:
        print(f"Unknown types: {sorted(unknown)} (choose from {list(TYPES)})", file=sys.stderr)
        return 1

    if args.ttb_id:
        if len(wanted) != 1:
            print("--ttb-id needs exactly one --types value", file=sys.stderr)
            return 1
        n = pull_by_id(wanted[0], args.ttb_id, api_key=key, sleep=args.sleep,
                       progress=lambda m: print(" ", m))
        print(f"{wanted[0]}: pulled {n} COLA(s) by id")
        return 0

    if args.backfill_registry:
        for tname in wanted:
            n = backfill_registry(tname, api_key=key, sleep=args.sleep,
                                  progress=lambda m: print(" ", m))
            print(f"{tname}: registry backfilled for {n} entries")
        return 0

    if args.backfill_panels:
        for tname in wanted:
            n = backfill_panels(tname, api_key=key, sleep=args.sleep,
                                progress=lambda m: print(" ", m))
            print(f"{tname}: backfilled {n} entries")
        return 0

    totals = {}
    for tname in wanted:
        print(f"\n=== {tname} ===")
        totals[tname] = pull_type(tname, api_key=key, per_type=args.per_type,
                                  query=args.query, from_date=args.from_date,
                                  sleep=args.sleep, progress=lambda m: print(" ", m))
        print(f"wrote {totals[tname]} entries")

    print(f"\nDone: {totals}. The UI auto-registers these as eval sets "
          f"(restart the server / refresh the page).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
