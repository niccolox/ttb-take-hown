# Removing PaddleOCR and Running Nemotron-Only — Feasibility

Research date: 2026-08-02. Question: can paddle be removed so nemotron
OCR v2 is the sole engine? Empirically grounded: all 15 golden images
swept through the real `/api/verify` endpoint under BOTH engines on this
machine (same applications built from `manifest.json` truth; nemotron via
the `docker-compose.gpu.yml` sidecar on the RTX 3050 Ti, paddle native).
Raw sweeps: scratchpad `paddle.json` / `nemotron.json` (session-local).
Companion docs: `nemotron-ocr-local-dev.md` (verified run),
`hosting-economics-two-vs-one-container.md` (cost model).

## Verdict up front

**No — removal fails today on correctness, and separately on economics
and ops.** The statutory-warning exact-text check — the product's core
check — regresses on 8 of 15 goldens under nemotron. The empirical sweep
actually strengthens the case for the *opposite* architecture: keep the
seam, run paddle as default, use nemotron where it demonstrably wins
(degraded photos, latency) — i.e. the E4 dual-engine telemetry direction
(gate decision: KEEP).

## The sweep, in numbers

- **Field-status agreement: 67/84 (80%).** 17 fields differ.
- **Latency: nemotron median 247 ms vs paddle 5,165 ms** per full verify
  (paddle on the powersave governor; against the recorded 2.9 s smoke
  baseline nemotron is still ~12× faster).

### Nemotron regressions (removal blockers)

1. **Statutory warning text fails on 8/15 goldens** that paddle passes
   (`statutory_text_differs`). Root cause verified at the raw-OCR layer:
   nemotron drops standalone single-character words in dense small print
   ("drive a car" → "drive car"). **Deterministic per image** (3/3
   identical runs on spirits_clean, 65 words each time) but borderline
   across the corpus — malt_clean flipped MATCH↔MISMATCH between two
   invocations. A screening tool whose flagship check false-alarms on
   most clean labels is unusable; a fix must come from preprocessing
   (upscale/tiling) or engine modes, and is unproven.
2. **Rotation/skew breaks reading order.** photo_skew: brand located as
   "Old Tom Distilled", class as "Kentucky DISTILLERY Straight Bourbon
   Whiskey" → two false MISMATCHes. Paddle's textline-orientation
   preprocessing handles this; the nemotron path has no equivalent.
3. **False assertion beats honest unknown.** photo_lowres: paddle says
   NEEDS_REVIEW (`not_visible_in_image`/`unreadable`) where nemotron
   asserts MISMATCH on the warning. For the "screening, never approval"
   posture, wrongly asserting a violation is worse than declaring the
   image unreadable.

### Nemotron wins (why the engine still earns its sidecar)

- **Degraded-photo recall:** photo_blur_dark class_type MATCH (paddle:
  unreadable); photo_lowres brand + net_contents MATCH (paddle:
  ambiguous/unreadable).
- **Latency:** 247 ms median end-to-end — changes the interactive UX and
  batch throughput math entirely.
- **trap_all_bold_warning:** nemotron flags the intended
  `weight_contrast_violation`; in this sweep paddle returned MATCH —
  a paddle miss worth investigating separately (the contrast check reads
  the located bbox region, so engine box geometry feeds it).

## What paddle uniquely provides today (what removal forfeits)

| Capability | Paddle | Nemotron-only |
|---|---|---|
| CPU-only inference | yes (that's prod) | **impossible as shipped** — CUDA extension mandatory, no ONNX/CPU path (researched, closed) |
| Hosting floor | ~$49/mo (App Service B3) | $73/mo commercial (ACA T4, arch-7.5 rebuild unverified); Gov $414 PAYG / $76 Spot |
| Prod image | python-slim, models baked, no egress | NGC pytorch base ~20 GB |
| CI / dev machines | any laptop, GitHub runners | GPU required everywhere; OCR-path tests need GPU runners or mocks |
| Orientation/skew | textline-orientation preproc | none in current path |
| Statutory small print | passes all goldens | fails 8/15 |
| Licensing | Apache paddle pins (3.2.2/3.2.0, load-bearing) | NVIDIA Open Model License (fine); no NVAIE for Route B |

The assignment's no-egress/firewall story and the PLAN.md premise were
built around the CPU column. Removing paddle is a one-way door out of
that posture.

## What would have to be true before removal (revisit checklist)

1. Small-print recall fixed and proven: preprocessing experiment
   (2-3× upscale of low-height text bands, or tiling) clears the warning
   check on all 15 goldens plus the napa corpus — M1 `eval-compare` is
   the instrument.
2. Deskew/orientation preprocessing added ahead of the engine (or an
   engine mode that handles it), photo_skew green.
3. Confidence calibration so unreadable degrades to NEEDS_REVIEW, never
   asserted MISMATCH (ties into the planned CONF_FLOOR retune + numeric
   L1-only floor).
4. A GPU CI answer (self-hosted runner or recorded-OCR fixtures) so the
   suite still runs.
5. Hosting sign-off at the duty cycle actually observed (economics doc).

Until all five hold, nemotron-only is not a candidate; with them it
becomes an M2+ decision, still gated on the PLAN.md premise.

## Recommendation

Keep the `Extractor` seam exactly as shipped: **paddle default, nemotron
opt-in** (`LABELCHECK_EXTRACTOR=nemotron`). Harvest nemotron's real wins
via E4 dual-engine telemetry (run-both-compare on NEEDS_REVIEW fields,
or nemotron as the degraded-photo second opinion) rather than replacing
the engine that currently carries the flagship check. File the paddle
all-bold-trap miss as its own investigation.
