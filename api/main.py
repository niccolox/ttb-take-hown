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
from .verify import verify

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


CORPORA = {"golden": Path(__file__).parent / "eval" / "golden",
           "napa": Path(__file__).parent / "eval" / "napa"}


def _corpus_items(name: str):
    base = CORPORA[name]
    manifest = json.loads((base / "manifest.json").read_text())
    items = []
    for m in manifest:
        if name == "napa":
            app_data = m["application"]
            note = m.get("expect", "")
        else:
            t = m.get("truth", {})
            app_data = {"beverage_type": t.get("beverage_type", "unspecified"),
                        "brand_name": t.get("brand", ""),
                        "class_type": t.get("class_type", ""),
                        "alcohol_content": t.get("abv_line") or "",
                        "net_contents": t.get("net_line") or ""}
            note = m.get("expect", "")
        items.append({"id": m["id"], "file": m["file"], "note": note,
                      "application": app_data,
                      "image": f"/api/corpus/{name}/image/{m['file']}"})
    return items


@app.get("/api/corpora")
def corpora():
    return [
        {"id": "golden", "label": "Golden set — 15 synthetic labels",
         "shows": "Clean controls plus every adversarial trap (title-case, all-bold, skew, glare…)."},
        {"id": "napa", "label": "Napa set — 8 real wine labels",
         "shows": "Real photographs (CC, Wikimedia): script fonts, occlusion, low-res, two-bottle frames."},
    ]


@app.get("/api/corpus/{name}")
def corpus(name: str):
    if name not in CORPORA:
        return JSONResponse({"error": "unknown corpus"}, status_code=404)
    return _corpus_items(name)


@app.get("/api/corpus/{name}/image/{fname}")
def corpus_image(name: str, fname: str):
    if name not in CORPORA:
        return JSONResponse({"error": "unknown corpus"}, status_code=404)
    allowed = {m["file"] for m in json.loads((CORPORA[name] / "manifest.json").read_text())}
    if fname not in allowed:                       # manifest-listed files only (no paths)
        return JSONResponse({"error": "unknown image"}, status_code=404)
    return FileResponse(CORPORA[name] / fname, media_type="image/jpeg")


@app.post("/api/verify")
async def api_verify(image: UploadFile = File(...), application: str = Form("{}")):
    if not extractor.ready():
        return JSONResponse({"error": "Still loading OCR models — try again in a few "
                                       "seconds.", "code": "warming_up"}, status_code=503)
    try:
        app_data = json.loads(application) if application else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "Application data wasn't valid JSON.",
                             "code": "bad_application_json"}, status_code=400)

    raw = await image.read()
    if len(raw) > MAX_BYTES:
        return JSONResponse({"error": "Image too large — max 8MB.",
                             "code": "too_large"}, status_code=413)
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))            # reopen after verify
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

    t0 = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
        img.save(tmp.name, "JPEG", quality=92)
        try:
            words = pool.submit(extractor.extract, tmp.name).result(timeout=15)
        except Exception:
            return JSONResponse({"error": "This check didn't finish — retry.",
                                 "code": "system_error"}, status_code=500)
    import numpy as np
    gray = np.array(img.convert("L"))
    result = verify(words, app_data, image_gray=gray)
    result["timing_ms"]["ocr"] = round((time.perf_counter() - t0) * 1000)
    return result


# static UI last so /docs, /redoc, /openapi.json stay reachable (DX spec)
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
