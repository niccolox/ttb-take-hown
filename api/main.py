"""FastAPI app: POST /api/verify, /healthz, sample endpoints, static UI.

Error taxonomy at the route boundary only (PLAN.md Section 2): named 4xx
responses with plain-language copy; system errors never become compliance
verdicts. /docs, /redoc, /openapi.json stay reachable (DX spec)."""

from __future__ import annotations

import io
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from .extractor import PaddleExtractor
from .verify import verify, verify_multi

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
GOLDEN = Path(__file__).parent / "eval" / "golden"
WEB = Path(__file__).parent / "web"

app = FastAPI(title="TTB Label Screening Assistant",
              description="Screening, never approval — the agent decides.")
extractor = PaddleExtractor()
pool = ThreadPoolExecutor(max_workers=2)

SAMPLES = {
    "clean_match": {
        "file": "spirits_clean.jpg", "label": "Clean match (bourbon)",
        "shows": "Everything matches — the all-clear state.",
        "application": {"beverage_type": "distilled_spirits",
                        "brand_name": "OLD TOM DISTILLERY",
                        "class_type": "Kentucky Straight Bourbon Whiskey",
                        "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}},
    "obvious_mismatch": {
        "file": "trap_abv_outside_band.jpg", "label": "Obvious mismatch (wrong ABV)",
        "shows": "Label prints 46% against a 45% application — outside the ±0.3 band.",
        "application": {"beverage_type": "distilled_spirits",
                        "brand_name": "OLD TOM DISTILLERY",
                        "class_type": "Kentucky Straight Bourbon Whiskey",
                        "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}},
    "titlecase_trap": {
        "file": "trap_titlecase_warning.jpg", "label": "Title-case warning trap",
        "shows": "The check Jenny caught by eye: 'Government Warning' in title case.",
        "application": {"beverage_type": "distilled_spirits",
                        "brand_name": "OLD TOM DISTILLERY",
                        "class_type": "Kentucky Straight Bourbon Whiskey",
                        "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}},
    "bad_photo": {
        "file": "photo_lowres.jpg", "label": "Bad photo → human review",
        "shows": "Unreadable input degrades honestly to NEEDS REVIEW, never a false verdict.",
        "application": {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
                        "class_type": "California Chardonnay — Table Wine",
                        "alcohol_content": "", "net_contents": "750 mL"}},
    "table_wine_no_abv": {
        "file": "wine_no_abv_table.jpg", "label": "Table wine, no ABV printed",
        "shows": "Missing ABV is legally compliant here → NOT REQUIRED, not a mismatch.",
        "application": {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
                        "class_type": "California Chardonnay — Table Wine",
                        "alcohol_content": "12.5%", "net_contents": "750 mL"}},
}


@app.on_event("startup")
def _warm():
    pool.submit(extractor.warm, str(GOLDEN / "spirits_clean.jpg"))


@app.get("/healthz")
def healthz():
    return {"status": "ready" if extractor.ready() else "loading models",
            "ready": extractor.ready()}


@app.get("/api/samples")
def samples():
    return [{"id": k, "label": v["label"], "shows": v["shows"],
             "application": v["application"], "image": f"/api/samples/{k}/image"}
            for k, v in SAMPLES.items()]


@app.get("/api/samples/{sid}/image")
def sample_image(sid: str):
    if sid not in SAMPLES:
        return JSONResponse({"error": "unknown sample"}, status_code=404)
    return FileResponse(GOLDEN / SAMPLES[sid]["file"], media_type="image/jpeg")


_EVAL = Path(__file__).parent / "eval"


def get_corpora() -> dict[str, Path]:
    """Resolved at request time so freshly pulled COLA Cloud sets register live."""
    out = {"golden": _EVAL / "golden", "napa": _EVAL / "napa"}
    cc = _EVAL / "colacloud"
    if cc.exists():
        for d in sorted(cc.iterdir()):
            if (d / "manifest.json").exists():
                out[f"colacloud_{d.name}"] = d
    return out


def _corpus_items(name: str):
    base = get_corpora()[name]
    manifest = json.loads((base / "manifest.json").read_text())
    items = []
    for m in manifest:
        if "application" in m:                     # napa / colacloud style
            app_data = m["application"]
            note = m.get("expect") or m.get("note", "")
        else:                                      # golden truth mapping
            t = m.get("truth", {})
            app_data = {"beverage_type": t.get("beverage_type", "unspecified"),
                        "brand_name": t.get("brand", ""),
                        "class_type": t.get("class_type", ""),
                        "alcohol_content": t.get("abv_line") or "",
                        "net_contents": t.get("net_line") or ""}
            note = m.get("expect", "")
        files = m.get("files") or [{"file": m["file"], "panel": "front"}]
        reg = m.get("registry") or {}
        extras = {
            "fanciful_name": reg.get("fanciful_name") or "",
            "origin": reg.get("origin") or "",
            "vintage": str(reg["wine_vintage_year"]) if reg.get("wine_vintage_year") else "",
            "appellation": reg.get("wine_appellation") or "",
            "grape_varietals": "/".join(reg["grape_varietals"])
                               if reg.get("grape_varietals") else "",
        }
        app_data = {**{k: v for k, v in extras.items() if v}, **app_data}
        items.append({"id": m["id"], "file": m["file"], "note": note,
                      "application": app_data,
                      "registry": m.get("registry") or None,
                      "image": f"/api/corpus/{name}/image/{m['file']}",
                      "images": [{"panel": f_["panel"],
                                  "url": f"/api/corpus/{name}/image/{f_['file']}"}
                                 for f_ in files]})
    return items


@app.get("/api/corpora")
def corpora():
    base = [
        {"id": "golden", "label": "Golden set — 15 synthetic labels",
         "shows": "Clean controls plus every adversarial trap (title-case, all-bold, skew, glare…)."},
        {"id": "napa", "label": "Napa set — 8 real wine labels",
         "shows": "Real photographs (CC, Wikimedia): script fonts, occlusion, low-res, two-bottle frames."},
    ]
    for cid, path in get_corpora().items():
        if not cid.startswith("colacloud_"):
            continue
        n = len(json.loads((path / "manifest.json").read_text()))
        t = cid.split("_", 1)[1].replace("_", " ")
        base.append({"id": cid,
                     "label": f"COLA Cloud — {t} ({n} approved registry labels)",
                     "shows": "Real approved COLAs pulled from the public registry; "
                              "the registry record is the application ground truth."})
    return base


@app.get("/api/corpus/{name}")
def corpus(name: str):
    if name not in get_corpora():
        return JSONResponse({"error": "unknown corpus"}, status_code=404)
    return _corpus_items(name)


@app.get("/api/corpus/{name}/image/{fname}")
def corpus_image(name: str, fname: str):
    reg = get_corpora()
    if name not in reg:
        return JSONResponse({"error": "unknown corpus"}, status_code=404)
    manifest = json.loads((reg[name] / "manifest.json").read_text())
    allowed = {m["file"] for m in manifest}
    for m in manifest:
        allowed.update(f_["file"] for f_ in m.get("files") or [])
    if fname not in allowed:                       # manifest-listed files only (no paths)
        return JSONResponse({"error": "unknown image"}, status_code=404)
    return FileResponse(reg[name] / fname, media_type="image/jpeg")


# ── registry pipelines (COLA Cloud pulls, one per commodity) ─────────────────
import os as _os
import threading as _threading

_DOTENV = Path(__file__).parents[1] / ".env"


def _load_dotenv() -> None:
    """Load repo-root .env into os.environ (never overriding what's already
    set). Called at import AND re-checked on pipeline requests, so creating
    .env works for the native server (make serve) without a restart — docker
    compose users get the same file via env_file."""
    if not _DOTENV.exists():
        return
    for line in _DOTENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not _os.environ.get(k):
            _os.environ[k] = v


_load_dotenv()

PIPELINES: dict[str, dict] = {
    t: {"status": "idle", "message": "", "count": None}
    for t in ("wine", "beer", "spirits", "imported_wine", "champagne", "kentucky_whisky",
              "napa_zinfandel")}
_pipeline_lock = _threading.Lock()


_pull_serializer = _threading.Lock()   # one pull at a time — 3 concurrent pulls
                                       # blew the 10/min burst limit in testing


def _run_pipeline(tname: str, per_type: int, query: str | None):
    from .eval.colacloud_pipeline import (pull_type, recover_orphans,
                                          setup_logging, log as cclog)
    setup_logging()
    st = PIPELINES[tname]
    st.update(message="queued (one pull runs at a time)…")
    cclog.info("UI pipeline requested: type=%s per_type=%s query=%r", tname, per_type, query)
    with _pull_serializer:
        try:
            key = _os.environ["COLACLOUD_API_KEY"]
            recover_orphans(tname, api_key=key,
                            progress=lambda m: st.update(message=m))
            n = pull_type(tname, api_key=key, per_type=per_type, query=query,
                          progress=lambda m: st.update(message=m))
            st.update(status="done", count=n,
                      message=f"{n} approved labels in the set — load it below.")
            cclog.info("UI pipeline done: type=%s total=%d", tname, n)
        except Exception as e:                    # surfaced, never silent
            msg = str(e)
            if "429" in msg or "Too many" in msg:
                msg = "registry rate limit hit — what was fetched is saved; wait a minute and retry"
            st.update(status="error", message=f"Pull didn't finish: {msg[:150]} — retry.")


# ── session persistence (DuckDB) ─────────────────────────────────────────────

from . import session_store


@app.get("/api/session")
def session_get(summary: bool = False):
    data = session_store.session_summary() if summary else session_store.load_session()
    if data is None:
        return JSONResponse({"saved": False})
    return {"saved": True, **data}


@app.post("/api/session")
async def session_save(meta: str = Form("{}"),
                       images: list[UploadFile] = File(None)):
    """Snapshot the batch. `meta` = JSON [{file_name, state, override,
    application, result, panels: [{panel, file}]}]; `images` = the panel files
    in the exact order the panels appear across items."""
    try:
        items = json.loads(meta)
        assert isinstance(items, list)
    except Exception:
        return JSONResponse({"error": "Bad session metadata.", "code": "bad_meta"},
                            status_code=400)
    if len(items) > 200:
        return JSONResponse({"error": "Session too large (max 200 labels).",
                             "code": "too_large"}, status_code=413)
    uploads = list(images or [])
    expected = [(i, p) for i, it in enumerate(items) for p in it.get("panels") or []]
    if len(uploads) != len(expected):
        return JSONResponse({"error": "Panel image count doesn't match metadata.",
                             "code": "panel_mismatch"}, status_code=400)
    blobs = []
    total = 0
    for (idx, p), up in zip(expected, uploads):
        raw = await up.read()
        total += len(raw)
        if len(raw) > MAX_BYTES or total > 64 * 1024 * 1024:
            return JSONResponse({"error": "Session images too large.",
                                 "code": "too_large"}, status_code=413)
        blobs.append((idx, p.get("panel") or "front", p.get("file") or "",
                      up.content_type or "image/jpeg", raw))
    info = session_store.save_session(items, blobs)
    return {"saved": True, **info}


@app.get("/api/session/panel/{item_idx}/{panel}")
def session_panel(item_idx: int, panel: str):
    if panel not in ("front", "back", "main", "unknown"):
        return JSONResponse({"error": "Unknown panel."}, status_code=404)
    got = session_store.get_panel(item_idx, panel)
    if not got:
        return JSONResponse({"error": "No such panel."}, status_code=404)
    data, mime = got
    from fastapi.responses import Response
    return Response(content=data, media_type=mime)


@app.delete("/api/session")
def session_clear():
    session_store.clear_session()
    return {"saved": False}


@app.get("/api/pipelines")
def pipelines():
    _load_dotenv()                                 # pick up a freshly created .env
    key_set = bool(_os.environ.get("COLACLOUD_API_KEY"))
    return {"api_key_configured": key_set, "pipelines": PIPELINES}


@app.post("/api/pipelines/{tname}/run")
def run_pipeline(tname: str, per_type: int = 4, query: str | None = None):
    if tname not in PIPELINES:
        return JSONResponse(
            {"error": "unknown pipeline — see GET /api/pipelines for the list"},
            status_code=404)
    _load_dotenv()
    if not _os.environ.get("COLACLOUD_API_KEY"):
        return JSONResponse(
            {"error": "COLACLOUD_API_KEY isn't set. Put it in a .env file at the repo "
                      "root (cp .env.example .env) — no restart needed — or export it. "
                      "Free key: app.colacloud.us.",
             "code": "no_api_key"}, status_code=400)
    with _pipeline_lock:
        if PIPELINES[tname]["status"] == "running":
            return JSONResponse({"error": "This pull is already running."}, status_code=409)
        PIPELINES[tname].update(status="running", message="starting…", count=None)
    _threading.Thread(target=_run_pipeline, args=(tname, min(per_type, 10), query),
                      daemon=True).start()
    return {"started": tname}


@app.post("/api/verify")
async def api_verify(image: UploadFile = File(None),
                     images: list[UploadFile] = File(None),
                     application: str = Form("{}")):
    """Single `image` (back-compat) or multiple `images` (front/back panels)."""
    if not extractor.ready():
        return JSONResponse({"error": "Still loading OCR models — try again in a few "
                                       "seconds.", "code": "warming_up"}, status_code=503)
    try:
        app_data = json.loads(application) if application else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "Application data wasn't valid JSON.",
                             "code": "bad_application_json"}, status_code=400)

    uploads = [u for u in ([image] if image else []) + (images or []) if u]
    if not uploads:
        return JSONResponse({"error": "No image uploaded.", "code": "no_image"},
                            status_code=400)
    if len(uploads) > 4:
        return JSONResponse({"error": "At most 4 label panels per check.",
                             "code": "too_many_panels"}, status_code=400)

    import numpy as np
    panels = []
    t0 = time.perf_counter()
    for up in uploads:
        raw = await up.read()
        if len(raw) > MAX_BYTES:
            return JSONResponse({"error": "Image too large — max 8MB.",
                                 "code": "too_large"}, status_code=413)
        try:
            img = Image.open(io.BytesIO(raw))
            img.verify()
            img = Image.open(io.BytesIO(raw))        # reopen after verify
            if img.format not in ("JPEG", "PNG", "WEBP"):
                return JSONResponse({"error": "PNG or JPG only. iPhone photos: export as JPG.",
                                     "code": "bad_format"}, status_code=400)
            if img.width * img.height > MAX_PIXELS:
                return JSONResponse({"error": "Image dimensions too large (max 40MP).",
                                     "code": "too_many_pixels"}, status_code=413)
            img = ImageOps.exif_transpose(img).convert("RGB")   # EXIF orientation (E1)
            if max(img.size) > 2000:
                r = 2000 / max(img.size)
                img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
        except Exception:
            return JSONResponse({"error": "Couldn't read this image — the file may be "
                                           "corrupt.", "code": "decode_failed"}, status_code=422)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            img.save(tmp.name, "JPEG", quality=92)
            try:
                words = pool.submit(extractor.extract, tmp.name).result(timeout=15)
            except Exception:
                return JSONResponse({"error": "This check didn't finish — retry.",
                                     "code": "system_error"}, status_code=500)
        panels.append((words, np.array(img.convert("L"))))

    result = verify_multi(panels, app_data)
    result["timing_ms"]["ocr"] = round((time.perf_counter() - t0) * 1000)
    return result


# static UI last so /docs, /redoc, /openapi.json stay reachable (DX spec)
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
