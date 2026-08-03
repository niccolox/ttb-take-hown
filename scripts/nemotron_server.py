"""Thin OCR HTTP wrapper for Nemotron OCR v2 — runs INSIDE the GPU container
(docker-compose.gpu.yml bind-mounts this file; it is not part of the api app).

Endpoints:
  GET  /v1/health/ready  -> 200 {"ready": true} once the model is loaded, else 503
  POST /v1/ocr           -> raw image bytes in the body (any format PIL reads);
                            returns {"width", "height", "words": [{"text",
                            "conf", "box": [x1, y1, x2, y2]}]} in PIXEL coords.

Raw-bytes body (not multipart) keeps the client side stdlib-only — the api
image has no requests/httpx and the NGC base image needs no python-multipart.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading

from fastapi import FastAPI, Request, Response

log = logging.getLogger("uvicorn.error")
app = FastAPI()

_ocr = None
_lock = threading.Lock()  # pipeline concurrency is unproven on a 4 GB card


def _load() -> None:
    global _ocr
    from nemotron_ocr.inference.pipeline_v2 import NemotronOCRV2

    # A complete model_dir short-circuits the hub download (pipeline.py: "If
    # provided and complete, this path is used and lang is ignored") — the
    # compose mounts the HF clone at /workspace, so startup needs zero egress.
    model_dir = os.environ.get("NEMOTRON_MODEL_DIR", "/workspace/v2_english")
    if os.path.isdir(model_dir):
        ocr = NemotronOCRV2(model_dir=model_dir)
    else:
        ocr = NemotronOCRV2(lang=os.environ.get("NEMOTRON_LANG", "en"))
    sample = "ocr-example-input-1.png"            # ships in the HF repo root
    if os.path.exists(sample):
        _predict(ocr, sample)                     # first-inference warmup
    with _lock:
        _ocr = ocr
    log.info("nemotron-ocr ready (model_dir=%s)", model_dir)


def _predict(ocr, path: str):
    try:
        return ocr(path, merge_level="word")      # word boxes feed the locator
    except TypeError:                             # older pipeline: no kwarg
        return ocr(path)


@app.on_event("startup")
def _warm() -> None:
    t = threading.Thread(target=_load, daemon=True)
    t.start()


@app.get("/v1/health/ready")
def ready(response: Response):
    ok = _ocr is not None
    response.status_code = 200 if ok else 503
    return {"ready": ok}


def _box(pred: dict, w: int, h: int) -> list[float]:
    # pipeline_v2 returns NORMALIZED coords with flipped y naming: "upper" is
    # max-y and "lower" is min-y (see its _process_batch formatter). Emit a
    # conventional (x1, y1, x2, y2) = (min, min, max, max) pixel box.
    x1, x2 = sorted((float(pred["left"]), float(pred["right"])))
    y1, y2 = sorted((float(pred["upper"]), float(pred["lower"])))
    if max(x2, y2) <= 1.001:                      # normalized -> pixels
        x1, x2 = x1 * w, x2 * w
        y1, y2 = y1 * h, y2 * h
    return [x1, y1, x2, y2]


# AD-21 (PLAN-enrichment N1): inference must never run on the event loop —
# it froze /v1/health/ready during every request, so callers misdiagnosed
# "busy" as "down". Work runs in one executor thread (the pipeline is not
# thread-safe; one instance, one worker); a bounded counter sheds with 503
# + queue depth instead of stacking waiters invisibly.
_MAX_WAITING = 8
_waiting = 0
_waiting_lock = threading.Lock()


def _ocr_sync(body: bytes) -> dict:
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        tmp.write(body)
        tmp.flush()
        with Image.open(tmp.name) as im:
            w, h = im.size
        with _lock:
            preds = _predict(_ocr, tmp.name)
    return {"width": w, "height": h,
            "words": [{"text": p["text"], "conf": float(p.get("confidence", 1.0)),
                       "box": _box(p, w, h)} for p in preds]}


@app.post("/v1/ocr")
async def ocr_endpoint(request: Request, response: Response):
    global _waiting
    if _ocr is None:
        response.status_code = 503
        return {"error": "model still loading"}
    with _waiting_lock:
        if _waiting >= _MAX_WAITING:
            response.status_code = 503
            return {"error": "queue full", "queue_depth": _waiting}
        _waiting += 1
    try:
        body = await request.body()
        import anyio
        return await anyio.to_thread.run_sync(_ocr_sync, body)
    finally:
        with _waiting_lock:
            _waiting -= 1


@app.get("/v1/health/queue")
def queue_depth():
    with _waiting_lock:
        return {"queue_depth": _waiting, "max_waiting": _MAX_WAITING}
