# Nemotron Best Practices + Two-Tier Async Pipeline Architecture

Research date: 2026-08-02. Question: best practices for Nemotron OCR v2,
and an architecture that returns results **under 5 seconds** (fast path)
while **background jobs run additional layers** that refine the verdict.
Sources: pipeline source in the HF repo, NIM docs, NVIDIA NeMo-Retriever
(ex nv-ingest, pushed 2026-07-31) — URLs at end. Empirical grounding:
`removing-paddle-nemotron-only.md` (15-golden A/B, 247 ms vs 5,165 ms
median). Companion: `nemotron-ocr-local-dev.md`, TODOS.md items this
absorbs.

## Part 1 — Best practices (what NVIDIA's code and pipelines actually do)

1. **The model is single-scale at 1024 px — and that explains our
   small-print dropout.** `pad_to_square` → resize to
   `infer_length × infer_length`, default 1024 (`_DEFAULT_INFER_LENGTH`;
   the README's "automatic multi-scale resizing" is NOT in the code).
   Our 1000×1400 goldens pad to 1400² then downscale to 1024² — the
   warning small print loses ~27% linear resolution before detection.
   Two supported levers: **raise `infer_length`** (constructor kwarg), or
   **OCR crops instead of pages** — the latter is NVIDIA's own pattern
   (NeMo-Retriever runs OCR on YOLOX page-element crops, never bare
   pages). Upscaling the input image does nothing (resized back down).
2. **One pipeline instance per worker, never threads.** The pipeline
   object holds mutable state and is not thread-safe. NVIDIA's pattern:
   one instance per Ray actor, **0.1 GPU per actor, 3 initial / 10 max
   actors per GPU** (English engine is 1.6–2.2 GiB, so ~10 fit). Our
   sidecar's single instance behind a lock is the n=1 degenerate case —
   correct, and scaling is "more actors," not "share the object."
3. **`merge_level="word"` is the right call for us** — per-word
   confidence aggregation at sentence/paragraph level is undocumented.
   Mode tradeoffs (README): `detector_only` −37% VRAM / +20% speed
   (boxes only); `skip_relational` −35% VRAM / +8% speed (words without
   reading order — reading order is what broke on photo_skew, so this is
   also a diagnostic knob).
4. **Confidence is the recognizer's geometric-mean token probability**
   (full pipeline) — not a detector score, not calibrated, and NVIDIA
   publishes no thresholds; NeMo-Retriever ignores confidence entirely
   downstream. Direct input to our CONF_FLOOR retune: paddle-tuned
   thresholds (verify.py) do NOT transfer; nemotron needs its own
   calibration curve from M1 data.
5. **No deskew exists anywhere in NVIDIA's stack** — detector emits
   rotated rects, but no orientation normalization, and the only public
   quality complaint (HF discussion #7) is exactly perspective/rotation.
   Rectification is on us (matches our photo_skew regression).
6. **Reference architecture is staged actors with bounded queues:**
   NeMo-Retriever composes operator graphs over Ray Data actor pools;
   the older nv-ingest used queue edges (size 64) with backpressure and
   PID autoscaling; JobSpec decides which stages run (their fast-path vs
   enrichment split). Remote OCR calls: 16 pool workers, 10 retries,
   structured error rows that never crash a batch. Also: a community PR
   (HF #8) shows 2.24× throughput from stream-aware serving — stock
   pipeline has per-call sync overhead; watch upstream, don't fork.

## Part 2 — Proposed architecture: fast path + refinement layers

Engine-symmetric two-tier design. The fast path uses the profile's
primary engine (paddle in the CPU profile — today's ratified default;
nemotron in the GPU profile); background layers refine. Nothing here
reverses the premise gate — the GPU profile stays opt-in until M1.

```
POST /api/verify  ──► S0 intake ──► S1 OCR ──► S2 locate+verify ──► provisional result
                       (≤5s hard budget; measured ~0.6s GPU / ~3s CPU)      │
                                                                    result_id + pending flags
       background job queue (per-field triggers, ~1-8s later)               │
       L2 small-print escalation ─┐                                         ▼
       L3 cross-engine check      ├──► conservative tier-merge ──► GET /api/verify/{id}
       L4 region quality/contrast ┘         (NOT _MERGE_RANK)          (poll or SSE)
       L5 VLM assist (existing TODO, last resort)
```

**S0 intake (new stage, ~50 ms):** decode, EXIF-rotate, and a cheap
skew estimate (binarize → min-area-rect on the text mass; rotate if
|angle| > ~2°). Fixes the photo_skew reading-order scramble for BOTH
engines at the one place it belongs (best practice #5: nobody deskews
for you).

**S1 fast OCR (~250 ms GPU / ~2.5 s CPU):** current engines unchanged,
`merge_level="word"`.

**S2 locate + verify:** current locator/rules path. New: each field
result carries `refinable` flags (e.g. warning MISMATCH with only
small-glyph diffs → refinable by L2; any NEEDS_REVIEW → refinable by
L3/L5). Response returns immediately with `result_id` — well under the
5 s budget in both profiles.

**L2 — small-print escalation (the dropout fix, GPU profile):** crop
the located warning band (fallback: bottom third), post the CROP to the
sidecar. A ~900×90 px crop enters the 1024² window at ~3× the effective
resolution of the full page — NVIDIA's own crop pattern applied to our
known failure. **VERIFIED live on this machine (2026-08-02):** cropping
spirits_clean's warning band (60,1100)-(960,1225) and re-OCRing recovers
BOTH words the full-page pass drops — `drive / a / car / or` come back
contiguous, correctly ordered, conf 0.92-0.94. The canonical dropout
case is fixed by exactly this stage. Alternative/additional lever: a
second sidecar pipeline instance with `infer_length=2048` for full-page
re-reads (VRAM allows it several times over). Absorbs TODOS
"retry-with-escalation extraction" with the latency moved off the
interactive path.

**L3 — cross-engine check (E4 dual-engine telemetry, KEEP at gate):**
re-verify flagged fields with the OTHER engine. Agreement upgrades
NEEDS_REVIEW→assertion or confirms; disagreement is always
NEEDS_REVIEW. Every L3 run logs the per-field engine pair — this IS the
E4 telemetry stream, and it accumulates M1 evidence in production.

**L4 — region quality/contrast:** weight-contrast + blur/contrast
metric on refined boxes (absorbs "warning region quality gate" TODO;
also the fix path for the paddle all-bold trap miss — refined boxes
feed the contrast check).

**L5 — VLM assist:** existing P3 TODO, unchanged candidate order,
triggered only when L2+L3 both fail to resolve a NEEDS_REVIEW.

**Conservative tier-merge (hard rule):** the logged eng learning stands
— multi-tier results must NOT flow through `verify_multi`'s
`_MERGE_RANK` (L2 MATCH would silently override L1 NEEDS_REVIEW). A
separate `merge_refinement(base, refined) -> FieldResult` with:
upgrades to MATCH require **two independent agreeing reads**; any
downgrade (MATCH→worse) applies immediately; every change records
provenance `(layer, engine, params)` for the audit trail.

### Job mechanics (smallest thing that works)

- **Precondition: the async event-loop P1 fix** (TODOS) — endpoints
  become sync `def`/executor-wrapped so background work can't freeze
  /healthz. This architecture is the payoff for doing it.
- In-process `asyncio`/thread job queue with bounded depth (queue-edge
  pattern, size ~64, shed with 503 when full — absorbs the "OCR timeout
  abandons the job" TODO by making jobs addressable and cancellable).
  No new infra: Ray/Redis is NVIDIA-scale, not 1-2-worker scale; the
  planned M3 job API is the natural home.
- Results: in-memory keyed by `result_id` with TTL; session saves
  persist final (post-refinement) state through the existing single
  DuckDB writer. Client: poll `GET /api/verify/{id}` (SSE later); UI
  shows a per-field "refining…" badge that settles within seconds.
- Sidecar server change (small): accept `infer_length` and crop
  parameters per request, or simply let the app post pre-cropped
  images (zero server change — preferred first step).

### Sequencing (each step ships alone)

1. S0 deskew + the async P1 fix (helps paddle today; no GPU needed).
2. Sidecar crop re-OCR + L2 escalation behind a flag; measure the
   8/15 warning regressions — expected to clear most (falsifiable via
   the golden sweep).
3. Job queue + `result_id` polling + provisional/refined UI states.
4. L3 cross-engine on flagged fields (E4 telemetry starts here).
5. L4 contrast on refined boxes; L5 VLM last.

## Explicitly unverified

- Crop re-OCR is verified on the canonical case (spirits_clean, above)
  but not yet swept across all 8 regressing goldens — step 2 measures
  the full clearance rate.
- `infer_length=2048` accuracy/VRAM behavior (kwarg exists; untested).
- S0 skew estimator quality on the photo corpus.
- `include_invalid=True` as an alternate dropout lever (prune condition
  not visible in the pipeline source).

Sources: huggingface.co/nvidia/nemotron-ocr-v2 (card, pipeline_v2.py,
discussions #7 #8) · huggingface.co/blog/nvidia/nemotron-ocr-v2 ·
docs.nvidia.com/nim/ingestion/image-ocr/latest (api-reference,
configuration, support-matrix, performance) · github.com/NVIDIA/
NeMo-Retriever (models/local/nemotron_ocr_v2.py, operators/extract/ocr/
gpu_ocr.py, common/modality/ocr/shared.py, ray_resource_hueristics.py,
graph/pipeline_graph.py) · docs.nvidia.com/nemo/retriever/latest/
extraction · deepwiki.com/NVIDIA/nv-ingest.
