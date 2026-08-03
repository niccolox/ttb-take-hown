"""Background refinement layers J1/J2 (PLAN-enrichment N3/N4).

J1 `second-engine-check`: re-verify every result with the QA engine
(paddle when nemotron is primary). Shadow mode writes per-field
engine-pair telemetry (the E4 stream); guard mode covers the statutory +
numeric fields — disagreement downgrades to NEEDS_REVIEW with BOTH reads
attached (AD-16), agreement marks the field guard-confirmed ("no
statutory MATCH ships without guard agreement").

J2 `warning-reread`: the verified fix for the full-page single-char
dropout — crop the located warning band, re-OCR the crop (3× effective
resolution inside the model's fixed 1024² window), splice the crop words
into the panel word list, re-run the pipeline, and merge the
government_warning field under AD-20 semantics: J2 is an authoritative
single read for statutory upgrades ONLY when J1's paddle read concurs.

Comparisons are normalized-text/status based, never box-geometry based
(AD-30 — paddle's synthetic word boxes vs nemotron's true boxes would
otherwise masquerade as disagreement).
"""

from __future__ import annotations

import io
import json
import logging
import tempfile
import threading
import time
from pathlib import Path

from .merge import GREEN, merge_refinement
from .verify import CONF_FLOOR_BY_ENGINE, verify_multi

log = logging.getLogger("uvicorn.error")

GUARD_FIELDS = ("government_warning", "alcohol_content", "net_contents")
J2_RETRY_CODES = {"statutory_text_differs", "ocr_confusable_punctuation",
                  "unreadable"}
TELEMETRY_PATH = Path(__file__).parent / "data" / "e4-telemetry.jsonl"
_telemetry_lock = threading.Lock()


def _telemetry(row: dict) -> None:
    try:
        TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _telemetry_lock:
            with open(TELEMETRY_PATH, "a") as f:
                f.write(json.dumps(row) + "\n")
    except OSError:                       # telemetry never breaks a verdict
        log.warning("e4 telemetry write failed", exc_info=True)


def _decode_panels(meta: dict):
    """Rebuild (words, gray) verify inputs from stored panel jpegs using the
    given extractor. Returns (panels, per-panel word lists)."""
    import numpy as np
    from PIL import Image
    grays = []
    for raw in meta["panels_jpeg"]:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        grays.append(np.array(img.convert("L")))
    return grays


def _extract_panel(extractor, raw: bytes):
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        tmp.write(raw)
        tmp.flush()
        return extractor.extract(tmp.name)


def _status_class(status: str) -> str:
    return "green" if status in GREEN else ("red" if status == "MISMATCH"
                                            else "review")


def run_j1(rid: str, store, qa_extractor, qa_engine: str, jobq,
           gpu_extractor=None, gpu_engine: str = "nemotron",
           gpu_available=lambda: True, vlm_client=None) -> None:
    """Second-engine QA. Chains J2 submission for qualifying warning fields
    (J2 needs J1's read for the AD-20 concurrence decision)."""
    entry = store.get(rid)
    if entry is None or entry.cancelled:
        return
    meta = entry.meta
    grays = _decode_panels(meta)
    panels = []
    for raw, gray in zip(meta["panels_jpeg"], grays):
        words = _extract_panel(qa_extractor, raw)
        panels.append((words, gray))
    qa_result = verify_multi(panels, meta["app_data"],
                             conf_floor=CONF_FLOOR_BY_ENGINE.get(qa_engine))
    qa_fields = {f["field"]: f for f in qa_result["fields"]}

    def apply(entry):
        for f in entry.result.get("fields", []):
            name = f["field"]
            qa = qa_fields.get(name)
            if qa is None:
                continue
            agree = _status_class(f["status"]) == _status_class(qa["status"])
            guard = name in GUARD_FIELDS
            _telemetry({"result_id": rid, "field": name,
                        "primary": {"engine": gpu_engine, "status": f["status"]},
                        "qa": {"engine": qa_engine, "status": qa["status"]},
                        "agree": agree, "guard": guard,
                        "ts": time.time()})
            if not guard:
                # shadow-recovery (AD-20 general rule): a primary read stuck at
                # NEEDS_REVIEW for a *read-quality* reason, where the QA engine
                # read the same region cleanly, has two independent agreeing
                # reads (QA exact + primary within-OCR-error) — upgrade with
                # corroboration. Ambiguous stays human (two candidate regions
                # is a layout question, not a read-quality one).
                if f["status"] == "NEEDS_REVIEW" \
                        and f.get("reason_code") in ("possible_ocr_misread",
                                                     "unreadable") \
                        and qa["status"] in ("MATCH", "LIKELY_MATCH"):
                    refined = {"status": qa["status"],
                               "label_value": qa.get("label_value"),
                               "reason_code": qa.get("reason_code"),
                               "note": (f"Second engine ({qa_engine}) read this "
                                        f"region cleanly and it matches the "
                                        f"application — two-engine agreement."),
                               "evidence": f.get("evidence")}
                    merge_refinement(f, refined, "second-engine-check",
                                     qa_engine, upgrade_ok=True)
                continue                    # otherwise shadow-only outside guard scope
            if agree:
                f["guard"] = {"state": "agreed", "engine": qa_engine,
                              "qa_status": qa["status"]}
            else:
                f["guard"] = {"state": "disagreed", "engine": qa_engine,
                              "qa_status": qa["status"],
                              "qa_label_value": qa.get("label_value"),
                              "qa_note": qa.get("note")}
                refined = {"status": "NEEDS_REVIEW",
                           "reason_code": "engine_disagreement",
                           "note": (f"Two OCR engines disagree here — "
                                    f"{gpu_engine} read: {f.get('label_value') or '(nothing)'} "
                                    f"[{f['status']}]; {qa_engine} read: "
                                    f"{qa.get('label_value') or '(nothing)'} "
                                    f"[{qa['status']}]. Check both crops."),
                           "label_value": f.get("label_value")}
                # upgrade_ok=True: moving red→NEEDS_REVIEW on disagreement IS
                # the ratified guard behavior (AD-16 — field locks at
                # NEEDS_REVIEW with both reads; the corroboration is the
                # second engine's differing read itself). Green→worse is a
                # downgrade and applies regardless.
                merge_refinement(f, refined, "second-engine-check", qa_engine,
                                 upgrade_ok=True)
        entry.meta["j1_fields"] = {n: {"status": q["status"],
                                       "label_value": q.get("label_value")}
                                   for n, q in qa_fields.items()}

    store.mutate(rid, apply)

    # chain J2 (N4): re-read the warning band at crop resolution when the
    # warning failed in a retryable class and the GPU engine is available
    entry = store.get(rid)
    if entry is None or entry.cancelled or gpu_extractor is None:
        return
    warn = next((f for f in entry.result.get("fields", [])
                 if f["field"] == "government_warning"), None)
    if warn and (warn.get("reason_code") in J2_RETRY_CODES
                 or (warn.get("guard") or {}).get("state") == "disagreed") \
            and gpu_available():
        jobq.submit(rid, "warning-reread",
                    lambda: run_j2(rid, store, gpu_extractor, gpu_engine,
                                   jobq=jobq, vlm_client=vlm_client),
                    deadline_s=30)
    elif vlm_client is not None and vlm_client.available():
        # no J2 needed — chain the VLM fallback reader directly (N5)
        jobq.submit(rid, "vlm-assist",
                    lambda: run_j3(rid, store, vlm_client), deadline_s=45)


VLM_QUESTIONS = {
    "government_warning": "Transcribe the government warning text printed in "
                          "this label crop exactly, word for word.",
    "alcohol_content": "What alcohol content statement is printed in this "
                       "label crop? Answer with just the printed text.",
    "net_contents": "What net contents statement is printed in this label "
                    "crop? Answer with just the printed text.",
}
DEFAULT_VLM_QUESTION = ("What text is printed in this label crop? Answer with "
                        "just the printed text.")
J3_MAX_FIELDS = 3               # hosted free tier is rate-limited; cap per label


def run_j3(rid: str, store, vlm_client) -> None:
    """VLM fallback reader (N5). Reads the CROPS of fields still flagged
    after J1/J2 and attaches suggestions — never a status change ("zero
    autonomous verdict changes" is the N5 exit criterion, and the
    hallucination data in the research is why)."""
    from PIL import Image

    entry = store.get(rid)
    if entry is None or entry.cancelled or not vlm_client.available():
        return
    meta = entry.meta
    targets = []
    for f in entry.result.get("fields", []):
        ev = f.get("evidence") or {}
        # evidence bbox is in ORIGINAL-bitmap coords by response time, but the
        # stored panel jpegs are the PROCESSED frame — use the pre-mapping
        # coords captured for J2 when present, else skip (crops only, never
        # a full panel)
        if f["status"] == "NEEDS_REVIEW" and ev.get("bbox"):
            targets.append(f)
        if len(targets) >= J3_MAX_FIELDS:
            break
    if not targets:
        return
    suggestions = {}
    for f in targets:
        ev = f["evidence"]
        p = ev.get("panel") or 0
        raw = meta["panels_jpeg"][p]
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        # map original-bitmap bbox back to processed frame: divide by scale
        # (the skew rotation makes exact inversion lossy; the axis-aligned
        # hull is fine for a question crop)
        s = (meta.get("scales") or [1.0])[p] if p < len(meta.get("scales") or []) else 1.0
        x1, y1, x2, y2 = [v / s for v in ev["bbox"]]
        m = 20
        box = (max(0, x1 - m), max(0, y1 - m),
               min(img.width, x2 + m), min(img.height, y2 + m))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        crop = img.crop(box)
        buf = io.BytesIO()
        crop.save(buf, "JPEG", quality=85)
        q = VLM_QUESTIONS.get(f["field"], DEFAULT_VLM_QUESTION)
        answer = vlm_client.read_crop(buf.getvalue(), q)
        if answer:
            suggestions[f["field"]] = {"suggestion": answer[:300], "question": q,
                                       "engine": "nano-vl-8b",
                                       "disclaimer": "AI-suggested — verify "
                                                     "against the label crop"}

    if not suggestions:
        return

    def apply(entry):
        for f in entry.result.get("fields", []):
            sug = suggestions.get(f["field"])
            if sug:
                f["vlm"] = sug
                f.setdefault("refinements", []).append(
                    {"layer": "vlm-assist", "engine": "nano-vl-8b",
                     "from": f["status"], "to": f["status"], "kind": "annotation",
                     "applied": False, "note": "suggestion attached, no status change"})

    store.mutate(rid, apply)


def run_j2(rid: str, store, gpu_extractor, gpu_engine: str,
           jobq=None, vlm_client=None) -> None:
    """Warning-band crop re-OCR + splice re-verify (the N4 fix)."""
    from PIL import Image

    from .locator import Word

    entry = store.get(rid)
    if entry is None or entry.cancelled:
        return
    meta = entry.meta
    panel_idx = meta.get("warn_panel", 0)
    raw = meta["panels_jpeg"][panel_idx]
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    band = meta.get("warn_bbox")
    if band:
        m = 25                                  # margin around the located band
        box = (max(0, band[0] - m), max(0, band[1] - m),
               min(img.width, band[2] + m), min(img.height, band[3] + m))
    else:
        box = (0, int(img.height * 2 / 3), img.width, img.height)  # fallback: bottom third
    crop = img.crop(box)
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=95)
    crop_words = _extract_panel(gpu_extractor, buf.getvalue())
    ox, oy = box[0], box[1]
    spliced_crop_words = [Word(text=w.text,
                               box=(w.box[0] + ox, w.box[1] + oy,
                                    w.box[2] + ox, w.box[3] + oy),
                               conf=w.conf) for w in crop_words]

    # rebuild the panel word list: original words OUTSIDE the band + crop words
    import numpy as np
    base_words = meta["panel_words"][panel_idx]
    kept = [w for w in base_words
            if not (box[0] <= (w.box[0] + w.box[2]) / 2 <= box[2]
                    and box[1] <= (w.box[1] + w.box[3]) / 2 <= box[3])]
    panels = []
    for i, praw in enumerate(meta["panels_jpeg"]):
        pimg = Image.open(io.BytesIO(praw)).convert("RGB")
        gray = np.array(pimg.convert("L"))
        words = (kept + spliced_crop_words) if i == panel_idx \
            else meta["panel_words"][i]
        panels.append((words, gray))
    re_result = verify_multi(panels, meta["app_data"],
                             conf_floor=CONF_FLOOR_BY_ENGINE.get(gpu_engine))
    re_warn = next((f for f in re_result["fields"]
                    if f["field"] == "government_warning"), None)
    if re_warn is None:
        return
    # map refined evidence to the client's original-bitmap frame (same
    # skew_tf → scale chain the fast path applies at response time)
    ev = re_warn.get("evidence")
    if ev:
        p = ev.get("panel") or 0
        s = (meta.get("scales") or [1.0])[p] if p < len(meta.get("scales") or []) else 1.0
        tf = (meta.get("skew_tfs") or [None])[p] if p < len(meta.get("skew_tfs") or []) else None

        def _map(bx):
            if tf is not None:
                bx = tf.box_to_pre(bx)
            return [round(v * s, 1) for v in bx]
        if ev.get("bbox"):
            ev["bbox"] = _map(ev["bbox"])
        for d in ev.get("diff_boxes") or []:
            d["box"] = _map(d["box"])

    # AD-20: J2 upgrades statutory text ONLY when J1's paddle read concurs
    j1 = (entry.meta.get("j1_fields") or {}).get("government_warning") or {}
    j1_green = j1.get("status") in GREEN

    def apply(entry):
        for f in entry.result.get("fields", []):
            if f["field"] != "government_warning":
                continue
            changed = merge_refinement(
                f, re_warn, "warning-reread", gpu_engine,
                upgrade_ok=j1_green, refresh_on_same=True,
                note=("re-read the warning band at crop resolution"
                      + ("" if j1_green else
                         " — clean re-read NOT applied: second engine did not concur")))
            if changed and f.get("guard", {}).get("state") == "disagreed" \
                    and j1_green and f["status"] in GREEN:
                f["guard"]["state"] = "agreed_after_reread"
        _telemetry({"result_id": rid, "field": "government_warning",
                    "layer": "warning-reread",
                    "primary": {"engine": gpu_engine, "status": re_warn["status"]},
                    "qa": {"engine": "paddle", "status": j1.get("status")},
                    "agree": j1_green and re_warn["status"] in GREEN,
                    "guard": True, "ts": time.time()})

    store.mutate(rid, apply)

    # chain the VLM fallback reader (N5) after the re-read settles — it only
    # looks at fields STILL flagged, so J2's upgrades shrink its work
    if jobq is not None and vlm_client is not None and vlm_client.available():
        jobq.submit(rid, "vlm-assist",
                    lambda: run_j3(rid, store, vlm_client), deadline_s=45)
