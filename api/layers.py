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
import os
import tempfile
import threading
import time
from pathlib import Path

from . import mm_judge
from .merge import GREEN, merge_refinement
from .verify import CONF_FLOOR_BY_ENGINE, verify_multi

log = logging.getLogger("uvicorn.error")

GUARD_FIELDS = ("government_warning", "alcohol_content", "net_contents")
J2_RETRY_CODES = {"statutory_text_differs", "ocr_confusable_punctuation",
                  "unreadable"}
TELEMETRY_PATH = Path(__file__).parent / "data" / "e4-telemetry.jsonl"
TELEMETRY_MAX_BYTES = 20 * 1024 * 1024   # audit F6: bounded, rotated once —
                                         # the N7 calibration set is ample at
                                         # 20MB; older halves age out as .1
_telemetry_lock = threading.Lock()


# re-audit R2: swallowed telemetry failures once hid HOURS of dropped
# calibration data (a root-owned file from a docker run). The guard stays —
# telemetry never breaks a verdict — but the drop COUNT is a health signal.
telemetry_drops = 0


def _telemetry(row: dict) -> None:
    global telemetry_drops
    try:
        TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _telemetry_lock:
            if TELEMETRY_PATH.exists() \
                    and TELEMETRY_PATH.stat().st_size > TELEMETRY_MAX_BYTES:
                TELEMETRY_PATH.replace(TELEMETRY_PATH.with_suffix(".jsonl.1"))
            with open(TELEMETRY_PATH, "a") as f:
                f.write(json.dumps(row) + "\n")
    except OSError:                       # telemetry never breaks a verdict
        telemetry_drops += 1
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


def _no_read(field: dict) -> bool:
    """An engine 'found nothing' here: no located text behind a review-class
    status. Absence of a second read is not a conflicting read — it must not
    veto the other engine's positive read (either direction)."""
    return not field.get("label_value") \
        and field.get("status") in ("NEEDS_REVIEW", "NOT_CHECKED")


def _map_evidence(ev: dict | None, meta: dict) -> dict | None:
    """QA-engine evidence boxes are in the PROCESSED frame; responses carry
    original-bitmap coords — map like the fast path does."""
    if not ev or not ev.get("bbox"):
        return ev
    p = ev.get("panel") or 0
    scales = meta.get("scales") or []
    tfs = meta.get("skew_tfs") or []
    s = scales[p] if p < len(scales) else 1.0
    tf = tfs[p] if p < len(tfs) else None

    def m(bx):
        if tf is not None:
            bx = tf.box_to_pre(bx)
        return [round(v * s, 1) for v in bx]
    ev = dict(ev)
    ev["bbox"] = m(ev["bbox"])
    if ev.get("diff_boxes"):
        ev["diff_boxes"] = [{**d, "box": m(d["box"])} for d in ev["diff_boxes"]]
    return ev


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
            single_read = (f["status"] in GREEN and _no_read(qa)) \
                or (_no_read(f) and qa["status"] in GREEN)
            _telemetry({"result_id": rid, "field": name,
                        "primary": {"engine": gpu_engine, "status": f["status"]},
                        "qa": {"engine": qa_engine, "status": qa["status"]},
                        "agree": agree, "guard": guard,
                        "single_read": single_read,
                        "ts": time.time()})
            if not guard:
                # shadow-recovery (AD-20 general rule): a primary read stuck at
                # NEEDS_REVIEW for a *read-quality* reason — or with NO read at
                # all — where the QA engine read the region cleanly, upgrades
                # with corroboration. Ambiguous stays human (two candidate
                # regions is a layout question, not a read-quality one).
                if f["status"] == "NEEDS_REVIEW" \
                        and (f.get("reason_code") in ("possible_ocr_misread",
                                                      "unreadable")
                             or _no_read(f)) \
                        and qa["status"] in ("MATCH", "LIKELY_MATCH"):
                    refined = {"status": qa["status"],
                               "label_value": qa.get("label_value"),
                               "reason_code": qa.get("reason_code"),
                               "note": (f"Second engine ({qa_engine}) read this "
                                        f"region cleanly and it matches the "
                                        f"application — two-engine agreement."),
                               "evidence": (_map_evidence(qa.get("evidence"), meta)
                                            if _no_read(f) else f.get("evidence"))}
                    merge_refinement(f, refined, "second-engine-check",
                                     qa_engine, upgrade_ok=True)
                continue                    # otherwise shadow-only outside guard scope
            if agree:
                f["guard"] = {"state": "agreed", "engine": qa_engine,
                              "qa_status": qa["status"]}
            elif f["status"] in GREEN and _no_read(qa):
                # one engine passed, the other had NO read here — absence
                # doesn't veto the positive read; the green stands, marked as
                # single-read so the provenance is honest
                f["guard"] = {"state": "agreed_single_read", "engine": qa_engine,
                              "qa_status": qa["status"],
                              "qa_note": "second engine had no read for this field"}
            elif _no_read(f) and qa["status"] in GREEN:
                # the QA engine found text the primary missed — a discovery
                # (applies immediately per AD-20's lattice), and the field
                # passes on that single located read
                refined = {"status": qa["status"],
                           "label_value": qa.get("label_value"),
                           "reason_code": qa.get("reason_code"),
                           "note": (f"{qa_engine} located this field where "
                                    f"{gpu_engine} found nothing — value matches "
                                    f"the application."),
                           "evidence": _map_evidence(qa.get("evidence"), meta)}
                merge_refinement(f, refined, "second-engine-check", qa_engine,
                                 upgrade_ok=True)
                f["guard"] = {"state": "agreed_single_read", "engine": qa_engine,
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

# mm second read (mm-ocr-augment D-3): transcribe-then-judge, gated by its
# OWN flag so the shipped question-mode assist is untouched when off and an
# ambient NVIDIA key can never activate the new path (amendment 10).
MM_FALLBACK_MIN_BUDGET_S = 20.0   # question fallback only with this much left
TERMINAL_NOT_DONE = frozenset({"timed_out", "cancelled", "failed",
                               "shed", "lost"})


def _mm_enabled() -> bool:
    return os.environ.get("LABELCHECK_MM_READ", "").strip().lower() \
        in ("1", "true", "on", "yes")


def run_j3(rid: str, store, vlm_client) -> None:
    """VLM fallback reader (N5). Reads the CROPS of fields still flagged
    after J1/J2 and attaches suggestions — never a status change ("zero
    autonomous verdict changes" is the N5 exit criterion, and the
    hallucination data in the research is why)."""
    from PIL import Image

    entry = store.get(rid)
    if entry is None or entry.cancelled:
        return
    # mm second read requires: the flag, a transcription-capable client,
    # and that mode's breaker closed (per-mode semantics, amendment 20)
    mm_on = (_mm_enabled() and hasattr(vlm_client, "transcribe_crop")
             and vlm_client.available("transcribe"))
    question_ok = vlm_client.available()
    if not mm_on and not question_ok:      # union at the point of use
        return
    meta = entry.meta
    # budget for the whole run — the question-mode fallback after a failed
    # transcription is allowed only while enough of the job's 45 s deadline
    # remains (amendment 18: never two full-timeout calls back to back)
    job = entry.jobs.get("vlm-assist")
    deadline_at = (job.submitted_at + job.deadline_s) if job is not None \
        else time.monotonic() + 45.0
    targets = []
    for f in entry.result.get("fields", []):
        ev = f.get("evidence") or {}
        # evidence bbox is in ORIGINAL-bitmap coords by response time, but the
        # stored panel jpegs are the PROCESSED frame — use the pre-mapping
        # coords captured for J2 when present, else skip (crops only, never
        # a full panel)
        # eligibility (amendment 17): MISMATCH rows join ONLY under the mm
        # flag — that's where sides_with_application lives; selection is
        # unchanged when the flag is off
        wanted = ("NEEDS_REVIEW", "MISMATCH") if mm_on else ("NEEDS_REVIEW",)
        if f["status"] in wanted and ev.get("bbox"):
            targets.append(f)
        if len(targets) >= J3_MAX_FIELDS:
            break
    if not targets:
        return
    engine = getattr(vlm_client, "engine_label", "nano-vl-8b")
    suggestions = {}
    mm_results = {}
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

        transcribed_ok = False
        if mm_on:
            t0 = time.monotonic()
            r = vlm_client.transcribe_crop(buf.getvalue())
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            if r.status == "error" and r.cause == "oversized":
                pass                       # registry posture: skip silently
            elif r.status == "ok":
                transcribed_ok = True
                try:
                    verdict, note = mm_judge.judge(
                        f["field"], f["status"], r.text,
                        meta.get("app_data") or {}, f.get("label_value"))
                except Exception as exc:   # judge bug ≠ dead layer (S2 map)
                    log.warning("mm judge failed for %s/%s: %r",
                                rid, f["field"], exc)
                    verdict, note = "error", "judge_exception"
                mm_results[f["field"]] = {
                    "text": r.text[:500], "verdict": verdict, "note": note,
                    "model": engine, "elapsed_ms": elapsed_ms}
            else:                          # unreadable | error(with cause)
                mm_results[f["field"]] = {
                    "verdict": r.status, "cause": r.cause,
                    "text": (r.text or "")[:500] or None,
                    "model": engine, "elapsed_ms": elapsed_ms}

        # question mode: the shipped path when mm is off; under mm it is
        # the ONE budget-gated fallback for NEEDS_REVIEW rows whose
        # transcription didn't produce judgeable text (never for the
        # widened MISMATCH rows — those are mm-only by design)
        want_question = (f["status"] == "NEEDS_REVIEW" and question_ok
                         and (not mm_on
                              or (not transcribed_ok
                                  and deadline_at - time.monotonic()
                                  >= MM_FALLBACK_MIN_BUDGET_S)))
        if want_question:
            q = VLM_QUESTIONS.get(f["field"], DEFAULT_VLM_QUESTION)
            answer = vlm_client.read_crop(buf.getvalue(), q)
            if answer:
                suggestions[f["field"]] = {"suggestion": answer[:300],
                                           "question": q, "engine": engine,
                                           "disclaimer": "AI-suggested — verify "
                                                         "against the label crop"}

    if not suggestions and not mm_results:
        return

    def terminal_not_done() -> bool:
        e2 = store.get(rid)
        j = e2.jobs.get("vlm-assist") if e2 is not None else None
        return j is not None and j.state in TERMINAL_NOT_DONE

    # late-mutation guard (amendment 19): a run that outlived its deadline
    # must not surface new verdicts on a result the user already saw settle
    if terminal_not_done():
        return

    def apply(entry):
        j = entry.jobs.get("vlm-assist")
        if j is not None and j.state in TERMINAL_NOT_DONE:
            return                          # raced the watchdog: no-op
        for f in entry.result.get("fields", []):
            sug = suggestions.get(f["field"])
            mm = mm_results.get(f["field"])
            if sug:
                f["vlm"] = sug
                f.setdefault("refinements", []).append(
                    {"layer": "vlm-assist", "engine": engine,
                     "from": f["status"], "to": f["status"], "kind": "annotation",
                     "applied": False, "note": "suggestion attached, no status change"})
            if mm:
                f["mm_reread"] = mm
                f.setdefault("refinements", []).append(
                    {"layer": "vlm-assist", "engine": engine,
                     "from": f["status"], "to": f["status"], "kind": "mm-reread",
                     "applied": False,
                     "note": f"second read: {mm['verdict']} — no status change"})

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
