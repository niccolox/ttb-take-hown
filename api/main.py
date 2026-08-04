"""FastAPI app: POST /api/verify, /healthz, sample endpoints, static UI.

Error taxonomy at the route boundary only (PLAN.md Section 2): named 4xx
responses with plain-language copy; system errors never become compliance
verdicts. /docs, /redoc, /openapi.json stay reachable (DX spec)."""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import layers as _layers_mod
from .extractor import build_extractor
from .intake import deskew
from .jobs import JobQueue, ResultStore
from .ratelimit import InflightGate, RateLimiter, allowed_hosts
from .verify import verify_multi

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
GOLDEN = Path(__file__).parent / "eval" / "golden"
WEB = Path(__file__).parent / "web"

app = FastAPI(title="TTB Label Screening Assistant",
              description="Screening, never approval — the agent decides.")
app.add_middleware(TrustedHostMiddleware,          # AD-31 Host validation
                   allowed_hosts=allowed_hosts())
rate_limiter = RateLimiter()
inflight_gate = InflightGate()
extractor = build_extractor()
PRIMARY_ENGINE = os.environ.get("LABELCHECK_EXTRACTOR", "paddle")
# AD-24: the GPU profile constructs and warms BOTH engines — paddle is the
# AD-1 fallback fast path and the J1 QA engine. CPU profile: single engine,
# no background layers.
qa_extractor = None
if PRIMARY_ENGINE == "nemotron" \
        and os.environ.get("LABELCHECK_JOBS", "on") != "off":
    from .extractor import PaddleExtractor
    qa_extractor = PaddleExtractor()
pool = ThreadPoolExecutor(max_workers=2)          # fast path ONLY (AD-23)
store = ResultStore()                             # single-process (AD-25)
jobq = JobQueue(store)                            # background layers (N3+)
from .vlm import NanoVLClient
vlm_client = NanoVLClient()                       # N5 J3; silent no-op without NVIDIA_API_KEY

# AD-26 circuit breaker: consecutive sidecar failures short-circuit GPU
# calls (fast path falls back to paddle; J2 jobs fail fast) until a cooloff.
_breaker = {"fails": 0, "until": 0.0}
_breaker_lock = threading.Lock()


def _gpu_ok() -> bool:
    with _breaker_lock:
        return _breaker["fails"] < 3 or time.monotonic() >= _breaker["until"]


def _gpu_result(success: bool) -> None:
    with _breaker_lock:
        if success:
            _breaker["fails"] = 0
        else:
            _breaker["fails"] += 1
            if _breaker["fails"] >= 3:
                _breaker["until"] = time.monotonic() + 30.0

# Wedge detection (AD-33): a native OCR call that hangs keeps its pool
# thread + engine lock forever; count timed-out-but-still-running extracts
# and stop reporting ready when the whole fast-path pool is wedged.
_wedged = 0
_wedge_lock = threading.Lock()


def _note_wedge(fut) -> None:
    global _wedged
    with _wedge_lock:
        _wedged += 1

    def _clear(_):
        global _wedged
        with _wedge_lock:
            _wedged -= 1
    fut.add_done_callback(_clear)


def _wedged_out() -> bool:
    with _wedge_lock:
        return _wedged >= pool._max_workers

SAMPLES = {
    "clean_match": {
        "training": [1, 'Lesson 1 — a clean pass: every check green, ready for sign-off.'],
        "file": "spirits_clean.jpg", "label": "Clean match (bourbon)",
        "shows": "Everything matches — the all-clear state.",
        "application": {"beverage_type": "distilled_spirits",
                        "brand_name": "OLD TOM DISTILLERY",
                        "class_type": "Kentucky Straight Bourbon Whiskey",
                        "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}},
    "obvious_mismatch": {
        "training": [2, 'Lesson 2 — a real defect: red verdict with the evidence that proves it.'],
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
        "training": [5, 'Lesson 5 — unreadable input degrades to review, never a fake verdict.'],
        "file": "photo_lowres.jpg", "label": "Bad photo → human review",
        "shows": "Unreadable input degrades honestly to NEEDS REVIEW, never a false verdict.",
        "application": {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
                        "class_type": "California Chardonnay — Table Wine",
                        "alcohol_content": "", "net_contents": "750 mL"}},
    "table_wine_no_abv": {
        "training": [3, 'Lesson 3 — the tool knows the rules: missing ABV is legal here (NOT REQUIRED).'],
        "file": "wine_no_abv_table.jpg", "label": "Table wine, no ABV printed",
        "shows": "Missing ABV is legally compliant here → NOT REQUIRED, not a mismatch.",
        "application": {"beverage_type": "wine", "brand_name": "SEABREEZE CELLARS",
                        "class_type": "California Chardonnay — Table Wine",
                        "alcohol_content": "12.5%", "net_contents": "750 mL"}},
}

# degraded wine pairs (front+back) from the per-pipeline golden set — the
# bad-photo conditions agents actually submit, with measured dispositions
_WINE_APP = {"beverage_type": "wine", "brand_name": "SEACLIFF ESTATE",
             "class_type": "California Chardonnay — Table Wine",
             "alcohol_content": "12.5%", "net_contents": "750 mL"}
SAMPLES.update({
    "wine_blur": {
        "training": [4, 'Lesson 4 — front + back pair, and honest ambers when the photo degrades.'],
        "label": "Blurry wine photo (front + back)",
        "shows": "Blur degrades honestly: unreadable fields go to review with crops — never a false mismatch.",
        "files": [("golden_cola/wine/gw_wine_blur_front.jpg", "front"),
                  ("golden_cola/wine/gw_wine_blur_back.jpg", "back")],
        "application": _WINE_APP},
    "wine_angle": {
        "label": "Wine photo at an angle (front + back)",
        "shows": "7° tilt: deskew recovers brand and warning; the long class phrase goes amber for a human.",
        "files": [("golden_cola/wine/gw_wine_angle_front.jpg", "front"),
                  ("golden_cola/wine/gw_wine_angle_back.jpg", "back")],
        "application": _WINE_APP},
    "wine_dark": {
        "label": "Poor lighting (front + back)",
        "shows": "Underexposed photo still verifies all-green.",
        "files": [("golden_cola/wine/gw_wine_dark_front.jpg", "front"),
                  ("golden_cola/wine/gw_wine_dark_back.jpg", "back")],
        "application": _WINE_APP},
    "wine_glare": {
        "label": "Flash glare (front + back)",
        "shows": "Glare washes the front; the back-label warning still verifies.",
        "files": [("golden_cola/wine/gw_wine_glare_front.jpg", "front"),
                  ("golden_cola/wine/gw_wine_glare_back.jpg", "back")],
        "application": _WINE_APP},
})


@app.on_event("startup")
def _warm():
    # AD-25: the result store lives in this process; a second worker would
    # 404 randomly on GET /api/verify/{id}. uvicorn --workers N sets
    # WEB_CONCURRENCY; refuse anything but 1.
    import os
    if os.environ.get("WEB_CONCURRENCY", "1") not in ("", "1"):
        raise RuntimeError("labelcheck requires a single worker process "
                           "(in-process result store, PLAN-enrichment AD-25)")
    fut = pool.submit(extractor.warm, str(GOLDEN / "spirits_clean.jpg"))
    fut.add_done_callback(                    # a swallowed warm-up error = silent forever-503
        lambda f: f.exception() and logging.getLogger("uvicorn.error").error(
            "extractor warm-up FAILED — /healthz will report loading forever: %r",
            f.exception()))
    if qa_extractor is not None:              # AD-24: warm the QA/fallback engine too
        qfut = jobq._executor.submit(qa_extractor.warm,
                                     str(GOLDEN / "spirits_clean.jpg"))
        qfut.add_done_callback(
            lambda f: f.exception() and logging.getLogger("uvicorn.error").error(
                "QA engine warm-up FAILED — J1/fallback unavailable: %r",
                f.exception()))


def _rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return 0.0


@app.get("/healthz")
def healthz():
    # AD-40 schema: `ready` keeps its historical meaning (can serve verdicts);
    # `state` is the tri-state (degraded_paddle arrives with N3's dual-engine).
    if _wedged_out():
        state, ready = "down", False
    elif extractor.ready() or (qa_extractor is not None and qa_extractor.ready()):
        # degraded_paddle (AD-24): sidecar tripped the breaker but the warmed
        # paddle fallback still serves verdicts — ready stays true
        if PRIMARY_ENGINE == "nemotron" and not _gpu_ok() \
                and qa_extractor is not None and qa_extractor.ready():
            state, ready = "degraded_paddle", True
        elif extractor.ready():
            state, ready = "ready", True
        else:
            state, ready = "loading", False
    else:
        state, ready = "loading", False
    return {"status": "ready" if ready else ("wedged" if state == "down"
                                             else "loading models"),
            "ready": ready, "state": state,
            "queue": {"depth": jobq.depth(), "oldest_age_s": jobq.oldest_age_s()},
            "rss_mb": _rss_mb(),
            # R2: nonzero means calibration/usage telemetry is being dropped
            # (permissions, disk) — silent-by-design at write time, loud here
            "telemetry_drops": _layers_mod.telemetry_drops}


@app.get("/api/samples")
def samples():
    out = []
    for k, v in SAMPLES.items():
        row = {"id": k, "label": v["label"], "shows": v["shows"],
               "application": v["application"],
               "image": f"/api/samples/{k}/image/0"}
        if v.get("training"):                 # curated lesson set (train-before-pilot T4)
            row["training"] = v["training"]
        if v.get("files"):                    # front+back pair (degraded wine set)
            row["images"] = [{"panel": p, "url": f"/api/samples/{k}/image/{i}"}
                             for i, (_f, p) in enumerate(v["files"])]
        out.append(row)
    return out


from .azure_openai import AzureOpenAIClient
from .review import run_ai_review
from .summary import (build_user_prompt, contradicts, decisions_trailer,
                      deterministic_record, system_for)

azoai_client = AzureOpenAIClient()   # silent no-op without AZ_OPENAI_* env
# troubled-application trigger: ≥50% of checked fields red/amber after the
# second layer settles → background AI triage review (D3: no client, no-op).
# Own daemon thread: a slow model call must never occupy a J-layer worker.
jobq.post_settle = lambda rid: threading.Thread(
    target=run_ai_review, args=(rid, store, azoai_client),
    name="labelcheck-ai-review", daemon=True).start()


@app.post("/api/verify/{result_id}/summary", include_in_schema=False)
async def pass_summary(result_id: str, request: Request):
    """Enrichment E3/E4 (PASS-scoped): after the agent records a whole-label
    PASS, draft a summary of the stored result. Display-layer only — the
    stored result is authoritative and unchanged; absent config → 204 and
    the UI shows nothing (D3). Metered like every POST (re-audit R1)."""
    ip = request.client.host if request.client else "unknown"
    ok, retry_after = rate_limiter.allow(ip)
    if not ok:
        return JSONResponse({"error": "rate_limited"}, status_code=429,
                            headers={"Retry-After": str(max(1, int(retry_after)))})
    if int(request.headers.get("content-length") or 0) > 2048:
        return JSONResponse({"error": "too_large"}, status_code=413)
    if os.environ.get("LABELCHECK_SUMMARY", "on") == "off":
        return Response(status_code=204, headers={"X-Summary-Skip": "flag_off"})
    if not azoai_client.available():
        return Response(status_code=204, headers={"X-Summary-Skip": "unavailable"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "bad_json"}, status_code=400)
    decision = body.get("decision")
    if decision not in ("PASS", "FAIL"):
        return JSONResponse({"error": "pass_or_fail_only"}, status_code=400)
    entry = store.get(result_id)
    if entry is None:
        return JSONResponse({"error": "unknown_result"}, status_code=404)
    result = entry.public()
    fields = result.get("fields") or []
    application = body.get("application") or {}
    if not isinstance(application, dict) or len(json.dumps(application)) > 1500:
        return JSONResponse({"error": "bad_application"}, status_code=400)
    # agent overrides ride the request (they live client-side until session
    # save): bounded, shape-checked, and only ever STATED in the summary as
    # agent decisions — the stored machine result stays authoritative
    overrides = body.get("overrides") or {}
    if not isinstance(overrides, dict) or len(json.dumps(overrides)) > 2000:
        return JSONResponse({"error": "bad_overrides"}, status_code=400)
    fld_ov = overrides.get("fields")
    if fld_ov is not None and (not isinstance(fld_ov, dict) or len(fld_ov) > 20
                               or any(not isinstance(v, dict) for v in fld_ov.values())):
        return JSONResponse({"error": "bad_overrides"}, status_code=400)
    text = azoai_client.complete(
        system_for(decision),
        build_user_prompt(fields, application, str(body.get("at") or "now"),
                          overrides=overrides, result=result, decision=decision))
    used_model = azoai_client.model
    disclaimer = "AI-assisted draft — verify before use"
    if not text:
        # the client IS configured but the model produced nothing (reasoning
        # models can burn the whole output cap deliberating) — the agent
        # still gets the record, built deterministically from the facts
        logging.getLogger("uvicorn.error").info(
            "summary: model returned no text for %s — deterministic fallback",
            result_id)
        text = deterministic_record(fields, str(body.get("at") or "now"),
                                    overrides, result, decision)
        used_model = "recorded facts (AI draft unavailable)"
        disclaimer = "Auto-generated from recorded facts — AI draft unavailable"
    if decision == "PASS" and contradicts(fields, text):
        _layers_mod._telemetry({"kind": "j4s", "event": "summary_contradiction",
                                "result_id": result_id, "at": time.time()})
        return Response(status_code=204, headers={"X-Summary-Skip": "contradiction"})
    # the decisions record is deterministic — composed from facts, never
    # left to the model (which proved willing to omit overrides)
    text = text.rstrip() + "\n\n" + decisions_trailer(
        fields, overrides, str(body.get("at") or "now"), decision=decision)
    return {"text": text, "model": used_model, "disclaimer": disclaimer}


_UI_EVENTS = {"tour_started", "tour_completed", "first_decision"}


@app.post("/api/telemetry", include_in_schema=False)
async def ui_telemetry(request: Request):
    """Train-before-pilot T5: local-only usage signals (time-to-first-
    decision, walkthrough completion) into the E4 stream — strict allowlist,
    no free text, never breaks anything. Re-audit R1: metered by the same
    per-IP bucket as /api/verify and body-capped — an unmetered write
    endpoint could churn the telemetry rotation and dilute calibration data."""
    ip = request.client.host if request.client else "unknown"
    ok, retry_after = rate_limiter.allow(ip)
    if not ok:
        return JSONResponse({"ok": False}, status_code=429,
                            headers={"Retry-After": str(max(1, int(retry_after)))})
    if int(request.headers.get("content-length") or 0) > 1024:
        return JSONResponse({"ok": False}, status_code=413)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)
    event = body.get("event")
    if event not in _UI_EVENTS:
        return JSONResponse({"ok": False}, status_code=400)
    row = {"kind": "ui", "event": event, "at": time.time()}
    ms = body.get("ms")
    if isinstance(ms, (int, float)) and 0 <= ms < 1e8:
        row["ms"] = round(float(ms))
    from .layers import _telemetry
    _telemetry(row)
    return {"ok": True}


@app.get("/api/samples/{sid}/image/{idx}")
def sample_image_panel(sid: str, idx: int):
    if sid not in SAMPLES:
        return JSONResponse({"error": "unknown sample"}, status_code=404)
    v = SAMPLES[sid]
    if v.get("files"):
        if not (0 <= idx < len(v["files"])):
            return JSONResponse({"error": "unknown panel"}, status_code=404)
        # paths are server-defined constants relative to api/eval — no user input
        return FileResponse(Path(__file__).parent / "eval" / v["files"][idx][0],
                            media_type="image/jpeg")
    return FileResponse(GOLDEN / v["file"], media_type="image/jpeg")


@app.get("/api/samples/{sid}/image")
def sample_image(sid: str):                   # legacy single-image URL
    return sample_image_panel(sid, 0)


_EVAL = Path(__file__).parent / "eval"


def get_corpora() -> dict[str, Path]:
    """Resolved at request time so freshly pulled COLA Cloud sets register live."""
    out = {"golden": _EVAL / "golden", "napa": _EVAL / "napa"}
    # synthetic per-pipeline goldens (full-res, controlled truth) sit beside
    # their real-corpus counterparts: golden_<pipeline> vs colacloud_<pipeline>
    gc = _EVAL / "golden_cola"
    if gc.exists():
        for d in sorted(gc.iterdir()):
            if (d / "manifest.json").exists():
                out[f"golden_{d.name}"] = d
    cc = _EVAL / "colacloud"
    if cc.exists():
        for d in sorted(cc.iterdir()):
            if (d / "manifest.json").exists():
                out[f"colacloud_{d.name}"] = d
    # load-test batches (gitignored; generate_batches.py) — registered when
    # present so the UI can one-click a 300-label physics run
    bt = _EVAL / "batches"
    if bt.exists():
        for d in sorted(bt.iterdir()):
            if (d / "manifest.json").exists():
                out[f"batch_{d.name}"] = d
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
            # app_abv is what the COLA declares; abv_line is what the label
            # prints. Falling back to abv_line here fed the label's own value
            # in as the application, which defeated the ABV traps (exact
            # match instead of band checks) and left the table wine blank.
            app_data = {"beverage_type": t.get("beverage_type", "unspecified"),
                        "brand_name": t.get("brand", ""),
                        "class_type": t.get("class_type", ""),
                        "alcohol_content": t.get("app_abv") or t.get("abv_line") or "",
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
    """Eval sets, grouped for the UI: `group` is "golden" (synthetic,
    controlled truth) or "cola" (real registry pulls)."""
    base = [
        {"id": "golden", "group": "golden",
         "label": "Golden set — 15 synthetic labels",
         "shows": "Clean controls plus every adversarial trap (title-case, all-bold, skew, glare…)."},
        {"id": "napa", "group": "golden",
         "label": "Napa set — 8 real wine labels",
         "shows": "Real photographs (CC, Wikimedia): script fonts, occlusion, low-res, two-bottle frames."},
    ]
    for cid, path in get_corpora().items():
        if cid.startswith("golden_"):
            n = len(json.loads((path / "manifest.json").read_text()))
            t = cid.split("_", 1)[1].replace("_", " ")
            base.append({"id": cid, "group": "golden",
                         "label": f"Golden — {t} ({n} synthetic, full-res)",
                         "shows": "Synthetic front+back pair patterned on this pipeline's "
                                  "real label structure; ground truth by construction."})
    for cid, path in get_corpora().items():
        if not cid.startswith("colacloud_"):
            continue
        n = len(json.loads((path / "manifest.json").read_text()))
        t = cid.split("_", 1)[1].replace("_", " ")
        base.append({"id": cid, "group": "cola",
                     "label": f"COLA Cloud — {t} ({n} approved registry labels)",
                     "shows": "Real approved COLAs pulled from the public registry; "
                              "the registry record is the application ground truth."})
    shown = 0
    for cid, path in get_corpora().items():
        if not cid.startswith("batch_") or shown >= 3:
            continue
        m = json.loads((path / "manifest.json").read_text())
        traps = sum(1 for x in m if str(x.get("expect", "")).startswith("MISMATCH"))
        pairs = sum(1 for x in m if len(x.get("files", [])) == 2)
        base.append({"id": cid, "group": "batch",
                     "label": f"Load test — {cid.split('_', 1)[1]} ({len(m)} labels)",
                     "shows": f"Batch physics: {traps} planted reds, {pairs} front+back "
                              f"pairs, degraded mix. Sessions don't save over 200 labels."})
        shown += 1
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
        return JSONResponse({"error": "unknown image", "code": "not_found"}, status_code=404)
    target = (reg[name] / fname).resolve()
    if not target.is_relative_to(reg[name].resolve()):   # containment even if a manifest lies
        return JSONResponse({"error": "unknown image", "code": "not_found"}, status_code=404)
    return FileResponse(target, media_type="image/jpeg")


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
def session_save(meta: str = Form("{}"),
                 images: list[UploadFile] = File(None)):
    """Snapshot the batch. `meta` = JSON [{file_name, state, override,
    application, result, panels: [{panel, file}]}]; `images` = the panel files
    in the exact order the panels appear across items."""
    try:
        items = json.loads(meta)
        assert isinstance(items, list)
        assert all(isinstance(it, dict) for it in items)
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
    VALID_PANELS = ("front", "back", "main", "unknown")
    MIME_BY_FORMAT = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
    blobs = []
    total = 0
    for (idx, p), up in zip(expected, uploads):
        raw = up.file.read()
        total += len(raw)
        if len(raw) > MAX_BYTES or total > 64 * 1024 * 1024:
            return JSONResponse({"error": "Session images too large.",
                                 "code": "too_large"}, status_code=413)
        # never store/replay a client-supplied MIME: validate the bytes are a real
        # image and choose the MIME from the actual format (stored-XSS guard)
        try:
            probe = Image.open(io.BytesIO(raw))
            probe.verify()
            mime = MIME_BY_FORMAT[probe.format]
        except Exception:
            return JSONResponse({"error": "Session panel is not a PNG/JPG/WEBP image.",
                                 "code": "bad_format"}, status_code=400)
        panel = p.get("panel") if p.get("panel") in VALID_PANELS else "unknown"
        blobs.append((idx, panel, p.get("file") or "", mime, raw))
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
    return Response(content=data, media_type=mime,
                    headers={"X-Content-Type-Options": "nosniff",
                             "Content-Disposition": "inline"})


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
def api_verify(request: Request,
               image: UploadFile = File(None),
               images: list[UploadFile] = File(None),
               application: str = Form("{}")):
    """Single `image` (back-compat) or multiple `images` (front/back panels).

    Sync `def` on purpose (N1): PIL decode/resize and the OCR wait run in
    FastAPI's threadpool, so /healthz and other requests stay live during a
    40 MP decode. Response carries the explicit finality contract (AD-34):
    `status`/`settled`/`revision`/`pending[]` — in N1 every result settles
    immediately (no background layers yet), so `status` is always
    "settled" and old consumers keep their semantics byte-identical."""
    ip = request.client.host if request.client else "unknown"
    ok, retry_after = rate_limiter.allow(ip)
    if not ok:
        return JSONResponse({"error": "Too many checks too quickly — wait a "
                                       "moment and retry.", "code": "rate_limited"},
                            status_code=429,
                            headers={"Retry-After": str(max(1, int(retry_after)))})
    if not inflight_gate.acquire():
        return JSONResponse({"error": "The screener is at capacity — retry in a "
                                       "few seconds.", "code": "busy"},
                            status_code=429, headers={"Retry-After": "3"})
    try:
        return _verify_impl(image, images, application)
    finally:
        inflight_gate.release()


def _verify_impl(image, images, application):
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
    scales = []                                  # OCR-space → original-bitmap factor per panel
    skew_tfs = []                                # S0 deskew inverse transforms (N2)
    panel_jpegs = []                             # processed panels, kept for J1/J2
    panel_words = []                             # primary-engine words per panel
    engines_used = []                            # per-panel engine (AD-1 fallback aware)
    t0 = time.perf_counter()
    for up in uploads:
        raw = up.file.read()
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
            scale_back = 1.0
            if max(img.size) > 2000:
                r = 2000 / max(img.size)
                pre_w = img.width
                img = img.resize((int(img.width * r), int(img.height * r)), Image.LANCZOS)
                scale_back = pre_w / img.width   # evidence boxes map back to the client's bitmap
            # NOTE (measured 2026-08-02): a 2x Lanczos upscale for small inputs
            # was A/B-tested on 700px-capped COLA CDN images — 16/16 fields
            # identical. Synthetic pixels don't help either engine; reverted.
            # The registry images cap at 700px at the SOURCE (COLA Cloud CDN
            # serves one rendition; TTB direct is bot-blocked) — higher-res
            # corpus requires original-resolution access from the provider.
            # S0 deskew (N2): both engines read straightened text; evidence
            # boxes come back in the rotated frame and are mapped to the
            # client's bitmap via box_to_pre + scale_back below
            img, skew_tf = deskew(img)
        except Exception:
            return JSONResponse({"error": "Couldn't read this image — the file may be "
                                           "corrupt.", "code": "decode_failed"}, status_code=422)
        jpeg_buf = io.BytesIO()
        img.save(jpeg_buf, "JPEG", quality=92)   # retained for background layers
        jpeg = jpeg_buf.getvalue()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
            tmp.write(jpeg)
            tmp.flush()
            use_fallback = (PRIMARY_ENGINE == "nemotron" and not _gpu_ok()
                            and qa_extractor is not None and qa_extractor.ready())
            eng = qa_extractor if use_fallback else extractor
            fut = pool.submit(eng.extract, tmp.name)
            try:
                words = fut.result(timeout=15)
                if eng is extractor:
                    _gpu_result(True)
            except TimeoutError:
                # the native call may be hung holding the engine lock — track
                # it so /healthz stops reporting ready if the pool wedges
                _note_wedge(fut)
                return JSONResponse({"error": "This check didn't finish — retry.",
                                     "code": "system_error"}, status_code=500)
            except Exception:
                # AD-1: sidecar failure degrades to the warmed paddle fallback
                # instead of failing the verify
                if eng is extractor and PRIMARY_ENGINE == "nemotron":
                    _gpu_result(False)
                    if qa_extractor is not None and qa_extractor.ready():
                        use_fallback = True
                        try:
                            words = qa_extractor.extract(tmp.name)
                        except Exception:
                            return JSONResponse(
                                {"error": "This check didn't finish — retry.",
                                 "code": "system_error"}, status_code=500)
                    else:
                        return JSONResponse(
                            {"error": "This check didn't finish — retry.",
                             "code": "system_error"}, status_code=500)
                else:
                    return JSONResponse({"error": "This check didn't finish — retry.",
                                         "code": "system_error"}, status_code=500)
        engines_used.append("paddle" if use_fallback or PRIMARY_ENGINE != "nemotron"
                            else "nemotron")
        panel_jpegs.append(jpeg)
        panel_words.append(words)
        panels.append((words, np.array(img.convert("L"))))
        scales.append(scale_back)
        skew_tfs.append(skew_tf)

    engine_for_floor = "paddle" if "paddle" in engines_used else PRIMARY_ENGINE
    from .verify import CONF_FLOOR_BY_ENGINE
    result = verify_multi(panels, app_data,
                          conf_floor=CONF_FLOOR_BY_ENGINE.get(engine_for_floor))
    # capture the warning band in PROCESSED-frame coords for J2 BEFORE the
    # response mapping below rewrites evidence to original-bitmap coords
    warn_bbox = warn_panel = None
    for f in result["fields"]:
        if f["field"] == "government_warning" and f.get("evidence", {}) \
                and f["evidence"].get("bbox"):
            warn_bbox = list(f["evidence"]["bbox"])
            warn_panel = f["evidence"].get("panel") or 0
            break
    # OCR ran on ≤2000px downscales; the browser draws crops on the ORIGINAL
    # bitmap — scale every evidence box back to original coordinates
    for f in result["fields"]:
        ev = f.get("evidence")
        if not ev:
            continue
        p = ev.get("panel") or 0
        s = scales[p] if p < len(scales) else 1.0
        tf = skew_tfs[p] if p < len(skew_tfs) else None
        if s != 1.0 or tf is not None:
            def _map(box):
                if tf is not None:
                    box = tf.box_to_pre(box)      # rotated → pre-rotation frame
                return [round(v * s, 1) for v in box]
            if ev.get("bbox"):
                ev["bbox"] = _map(ev["bbox"])
            for d in ev.get("diff_boxes") or []:
                d["box"] = _map(d["box"])
    result["timing_ms"]["ocr"] = round((time.perf_counter() - t0) * 1000)
    entry = store.put(result)                 # result_id == request_id (AD-36)
    rid = result["request_id"]
    # J1 second-engine QA (N3): only when the fast path actually ran the GPU
    # engine — a fallback verify already IS the paddle read (AD-24: J1
    # suspended while degraded)
    if qa_extractor is not None and qa_extractor.ready() \
            and "paddle" not in engines_used:
        entry.meta.update(panels_jpeg=panel_jpegs, panel_words=panel_words,
                          app_data=app_data, warn_bbox=warn_bbox,
                          warn_panel=warn_panel or 0, scales=scales,
                          skew_tfs=skew_tfs)
        from .layers import run_j1
        jobq.submit(rid, "second-engine-check",
                    lambda: run_j1(rid, store, qa_extractor, "paddle", jobq,
                                   gpu_extractor=extractor,
                                   gpu_engine="nemotron",
                                   gpu_available=_gpu_ok,
                                   vlm_client=vlm_client),
                    deadline_s=45)
    body = entry.public()
    body["cancel_token"] = entry.cancel_token  # only in the POST response (AD-39)
    return body


@app.get("/api/verify/{result_id}")
def api_verify_get(result_id: str):
    """Refinement lifecycle read (AD-34): poll until `settled` is true.
    `revision` is monotonic per result — clients apply a response only if
    its revision is >= the last one seen (AD-19/AD-32)."""
    entry = store.get(result_id)
    if entry is None:
        code = store.status_of_missing(result_id)   # expired ≠ not_found (AD-38)
        msg = ("This result expired — re-verify the label."
               if code == "expired" else "Unknown result id — re-verify the label.")
        return JSONResponse({"error": msg, "code": code}, status_code=404)
    return entry.public()


@app.post("/api/verify/{result_id}/cancel", include_in_schema=False)
def api_verify_cancel(result_id: str, token: str = Form("")):
    """Internal (AD-39): invoked by re-verify, gated by the POST-issued token."""
    entry = store.get(result_id)
    if entry is None:
        return JSONResponse({"error": "Unknown or expired result id.",
                             "code": store.status_of_missing(result_id)},
                            status_code=404)
    if token != entry.cancel_token:
        return JSONResponse({"error": "Bad cancel token.", "code": "bad_token"},
                            status_code=403)
    if entry.settled():
        return JSONResponse({"error": "Already settled — nothing to cancel.",
                             "code": "already_settled"}, status_code=409)
    jobq.cancel_result(result_id)
    return {"cancelled": True, "result_id": result_id}


# static UI last so /docs, /redoc, /openapi.json stay reachable (DX spec)
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
