<!-- /autoplan restore point: /home/niccolox/.gstack/projects/niccolox-treasury-instructions/main-autoplan-restore-20260802-162838.md -->
# PLAN-enrichment — Fast Nemotron Path + Background Enrichment (VLM + Azure LLM) + Paddle QA

Status: **APPROVED** at /autoplan final gate, 2026-08-02 (all recommendations incl. AD-9 as ratified). Exploratory-adjacent: builds
on the running `docker-compose.gpu.yml` stack and today's research
(`docs/research/nemotron-pipeline-architecture.md`,
`docs/research/document-intelligence-pipeline-nano-vl-azure.md`,
`docs/research/removing-paddle-nemotron-only.md`). Relationship to ratified
plans: PLAN.md (Rev 2.1) remains the shipped baseline; PLAN-us-stack.md
remains the exploratory US-stack paper plan. This plan proposes the GPU
deployment profile's runtime architecture. One premise here (N-P4, cloud
LLM enrichment) DEVIATES from PLAN.md's "no cloud ML" premise and is
flagged for the premise gate, not assumed.

## Context

Today's measurements changed the calculus: nemotron OCR end-to-end verify
median is 247 ms vs paddle's 5,165 ms (powersave; 2.9 s recorded normal),
but nemotron regresses the statutory-warning check on 8/15 goldens
(single-char dropout in small print — root-caused to the model's fixed
1024² inference window) while catching things paddle misses (all-bold
weight-contrast trap, degraded-photo fields). The crop re-OCR fix for the
dropout is verified live on the canonical case. This plan turns those
facts into a production architecture: a fast non-blocking path that
returns a provisional verdict in well under 5 s, with background
enrichment layers that refine it, and paddle running in parallel as a QA
pipeline.

## Premises (for the gate)

- **N-P1**: Sub-5s interactive response is a hard product requirement; the
  fast path must never block on enrichment. (Carried from PLAN.md's 5s
  budget.)
- **N-P2**: Nemotron becomes the GPU profile's fast-path engine DESPITE
  its current warning-check regression, BECAUSE (a) the L2 crop
  escalation that fixes it is verified on the canonical case and ships in
  the same milestone, and (b) paddle QA guard-mode catches statutory
  disagreements meanwhile. Paddle remains the CPU profile's default;
  PLAN.md's ratified default is unchanged outside the GPU profile.
- **N-P3**: Two engines with measured complementary error profiles
  (17/84 field disagreements, each catching the other's misses) justify a
  permanent parallel QA pipeline, not just an eval-time comparison.
- **N-P4 (RATIFIED at gate 2026-08-02, amended)**: An Azure-hosted LLM
  (Azure OpenAI) may be used for background enrichment of DERIVED TEXT
  ONLY (field values, OCR text, rule outcomes — never label images).
  **Amendment (user decision D3): J4 is best-effort by reachability —
  if the Azure endpoint is unreachable (firewall, outage, no key), the
  job completes as a silent no-op: no error in the verdict path, no UI
  degradation, telemetry row notes `enrichment_unavailable`.** This
  answers the reviewers' reachability objection (PLAN.md's "no cloud
  ML" premise traces to TTB's blocked outbound endpoints): behind the
  firewall the product is byte-identical to J4-absent behavior. Both
  review models recommended rejecting N-P4 outright; the user kept it
  with the silent-degradation amendment (logged as an informed
  override).

### Premise gate outcomes (2026-08-02)

- N-P1: accepted (uncontroversial, carried from PLAN.md).
- N-P2: **user override of both models** — nemotron flips to GPU-profile
  primary in N3 as written; both reviewers recommended gating the flip
  on the full 8-golden sweep. Mitigations that survive the override
  (they strengthen, not contradict): N3 exit adds "clean-label
  NEEDS_REVIEW rate under guard ≤ paddle baseline" and "same image →
  same final verdict 3/3 runs"; N4 remains scheduled immediately after
  N3.
- N-P3: amended to **calibration-period QA** — shadow/guard through N7;
  permanence decided from accumulated E4 telemetry at N7 exit. Batch
  degradation policy added: under batch load J1 drops to guard-only on
  statutory fields + sampled shadow (rate configurable), so the queue
  never backs up behind QA jobs.
- N-P4: kept with silent-degradation amendment (above).
- Sequencing (D4): **N1 → N2 → [deployed URL + P1 supply-chain
  hardening, outside this plan] → N3..N7.** The enrichment milestones
  resume only after the graded deliverables ship.

## Architecture (target state)

```
POST /api/verify (upload, exists)
  ─► S0 intake: decode, EXIF, deskew (~50 ms)
  ─► S1 nemotron OCR word-level (~250 ms GPU)
  ─► S2 locate + verify → PROVISIONAL verdict + result_id     [fast path ≤5 s hard, ~0.6 s measured]
        │ response carries per-field refinable flags + job manifest
  background jobs (bounded queue ~64, 503-shed, cancellable):
  ── J1 paddle QA (parallel, EVERY verify):
        shadow mode (default): per-field engine-pair telemetry (E4 stream)
        guard mode (statutory text + numeric fields only): disagreement
        → NEEDS_REVIEW with both reads shown; never silent MATCH
  ── J2 L2 crop re-OCR escalation (warning band; verified fix)
  ── J3 VLM layer — Nemotron Nano VL 8B (OCR-grounded, crops only):
        fallback reader / verifier / COLA-form structurer
  ── J4 Azure LLM enrichment (N-P4, text-only, feature-flagged OFF):
        reviewer-facing explanation drafts, class/type designation
        cross-check against CFR knowledge, never a verdict source
  merge: conservative merge_refinement() (NOT verify_multi._MERGE_RANK);
  MATCH upgrades need two agreeing reads; downgrades apply immediately;
  provenance (layer, engine, params) on every change
  ─► GET /api/verify/{result_id}: provisional → refined; UI shows
     per-field "refining…" badge; verdict changes surface as a visible
     upgrade event, never a silent swap
```

## Milestones

- **N1 — Async foundation.** Fix the async event-loop P1 (endpoints sync
  `def`/executor); in-process bounded job queue with result store + TTL;
  `GET /api/verify/{id}`; absorbs "OCR timeout abandons the job" TODO.
  No engine changes. Exit: /healthz stays live under a 40 MP decode +
  concurrent verifies; suite green.
- **N2 — S0 deskew intake.** Cheap skew estimate + rotate before OCR
  (both engines benefit; photo_skew golden is the acceptance test).
- **N3 — Nemotron fast path + paddle QA.** GPU profile flips primary
  engine to nemotron; paddle runs as J1 on every verify (shadow default,
  guard on statutory/numeric). Exit: golden sweep — provisional verdicts
  ≤1 s; no statutory MATCH ships without guard agreement; E4 telemetry
  rows written.
- **N4 — L2 crop escalation.** Warning-band crop re-OCR as J2; exit:
  the 8/15 warning regressions clear on the golden sweep (measured, not
  assumed); malt_clean flip-flop case stabilizes.
- **N5 — VLM layer (J3).** Nano VL 8B behind the Extractor-adjacent
  assist seam; three roles, OCR-grounded, crops only; laptop dev via
  build.nvidia.com free tier on golden/synthetic images only; Azure A10
  co-location per the hosting research. Exit: VLM suggestions appear on
  flagged fields with provenance; zero autonomous verdict changes.
- **N6 — Azure LLM enrichment (J4) — GATED on N-P4.** Feature-flagged
  OFF by default; text-only payloads; Azure OpenAI (Gov for real data);
  reviewer-facing drafts only. Exit: flag off = byte-identical behavior;
  flag on = drafts carry "AI-suggested, verify against label" labeling.
- **N7 — Calibration + report.** Nemotron CONF_FLOOR calibration from
  accumulated J1 telemetry (confidence = recognizer token-prob geomean,
  paddle thresholds don't transfer); merge M1 eval-compare deliverables.

## UI touch points (design scope)

- Per-field "refining…" badge component on the result panel while jobs
  are pending; settles within seconds.
- Verdict-upgrade event: a field that changes status after refinement
  gets a visible timeline entry (was MISMATCH → now MATCH via crop
  re-OCR), never a silent swap; the re-verify button and decided-state
  interactions must respect existing agent decisions (extends the
  "re-verify wipes decisions" TODO).
- Provenance popover per refined field: layer, engine, params.
- Guard-mode disagreement rendering: both engine reads side by side.

## DESIGN REVIEW (Phase 2, /autoplan, 2026-08-02) — [subagent-only; codex sandbox degraded]

Initial design completeness: **3/10** — engineering rigor (merge
semantics, freeze, failure registry) far ahead of design rigor; the
moments where an agent WATCHES a verdict move were one-line bullets.
Pass ratings pre-fix: IA 4, states 2, journey 3, slop-risk 5 (named-layer
copy already required), system-alignment 6 (FAMILY chips/override/stale
patterns exist and are reused), responsive/a11y 2, unresolved 5 major.
Post-fix (below): target 8+. Auto-decisions AD-9..AD-19:

- **AD-9 (borderline taste — surfaced at final gate): provisional
  actionability + sign-off gating.** Overrides allowed anytime; an agent
  decision on a field FREEZES that field against refinement mutation
  (AD-7 at field granularity; late refinements append as annotations).
  Whole-label sign-off is blocked with "checks still settling" while any
  guard/refinement job is pending (explicit override-confirm available).
  Downgrades get a stronger event class: persistent attention marker on
  field row AND batch-list row until opened.
- **AD-10 chip-state matrix.** {MATCH, MISMATCH, NEEDS_REVIEW} ×
  {provisional, refining, settled, refine-failed}: provisional = hollow/
  outlined chip in verdict color + layer-named suffix; settled = current
  solid chip; a provisional chip is never visually identical to settled.
- **AD-11 batch-list no-silent-swap.** Rows carry refinement-pending
  indicator; a row whose rollup changed post-refinement keeps a
  persistent "updated" marker until opened; list never reorders while
  refining.
- **AD-12 guard-scoped fields lead with process, not verdict.** Statutory
  text shows "verifying statutory text with second engine" (no
  provisional color) until guard agrees/disagrees.
- **AD-13 terminal job states.** GET reports per-job `shed`/`lost`;
  UI maps to settled-skipped ("additional checks skipped — high load"),
  60s poll force-settle. Every field ends in exactly one of:
  settled-confirmed / settled-changed / settled-skipped / settled-failed.
- **AD-14 refine-failure design.** Non-blocking marker + popover
  ("second-pass re-read failed — verdict from first pass only"); J2
  failure on a guard-scoped field downgrades to NEEDS_REVIEW.
- **AD-15 confirmation is rendered.** Settle-without-change transitions
  to settled visual + "confirmed by second engine" provenance note (the
  cheapest trust-builder; majority case must not be ambiguous with
  failure).
- **AD-16 disagreement resolution.** Two labeled reads, each with its
  OWN evidence crop; field locked NEEDS_REVIEW; resolution via the
  EXISTING per-field agent decision (no new verb); CSV exports both
  reads + agent decision.
- **AD-17 provenance popover is agent-first.** Old → new value/status,
  plain-language layer name, the NEW evidence crop + extracted text;
  params go to logs.
- **AD-18 status precedence rule.** agent override > settled machine
  verdict > provisional; staleness (⟳) and refining are orthogonal
  markers that never replace status; refinement never mutates an
  overridden field.
- **AD-19 poll spec.** 1s → backoff → stop at all-terminal or 60s; one
  active poller for the visible result, low-rate for backgrounded;
  client applies responses only with monotonically increasing
  `revision`.
- Cancel endpoint declared INTERNAL-only (invoked by re-verify); no UI
  control. 404-mid-session: stop polling, keep last-known render, mark
  pending fields settled-skipped (session expired).
- Trust copy requirement: every refinement state names its process
  ("re-reading warning text at full resolution"), and settle-time
  expectation shown from measured p95 (S8 collects it).
- Deliverable added to N3: **one-page component spec** (chip matrix
  anatomy, timeline placement/persistence/export, popover contents,
  disagreement panel, AD-1 banner) with actual copy strings.
- A11y: chip states must not be color-only (shape/outline + text);
  attention markers keyboard-reachable; popovers focus-managed
  (extends existing focus-restoration TODO).

## API surface (DX scope)

- `POST /api/verify` unchanged (back-compat) + `result_id` + `pending[]`
  in the response.
- `GET /api/verify/{result_id}` — full result with refinement states.
- `POST /api/verify/{result_id}/cancel` — cancel pending jobs.
- Job queue depth exposed on `/healthz` for ops.

## DX REVIEW (Phase 3.5, /autoplan, 2026-08-02) — voices: Claude subagent (file-grounded, 8) + Codex (digest, 8)

DX CONSENSUS: 1. <5-min start? both NO → fixed. 2. Naming guessable? both
partial → fixed. 3. Errors actionable? both underspecified → fixed.
4. Docs complete? both NO (empty OpenAPI schemas) → fixed. 5. Upgrade
safe? both NO (**semantic back-compat break — the shared #1**) → fixed.
6. Dev env friction? OK (existing /docs + smoke patterns reused).

Auto-decisions AD-34..AD-40:

- **AD-34 (the shared #1): finality is explicit, never inferred.** GET
  and POST responses carry top-level `status: "provisional"|"settled"`
  + `settled: bool` + `revision`. Flags-off/CPU profile: POST returns
  `status:"settled"`, `pending:[]` — byte-identical semantics for old
  consumers. Updating smoke.sh + eval harness + app.js to poll-until-
  settled is an N1/N3 EXIT CRITERION, and smoke's poll loop doubles as
  the back-compat regression test.
- **AD-35: schema-of-record section.** The API section gains concrete
  JSON examples for POST/GET/healthz (the contract accreted into AD-13/
  19/27/31/32 — consolidated); Pydantic response models so /docs renders
  real schemas; a two-command curl walkthrough (POST → `jq`-poll until
  `.settled`) in the README.
- **AD-36: one identifier.** `result_id == request_id` — the existing
  `request_id` is reused as the GET path key; no second id minted.
- **AD-37: stable capability names.** Job layers expose product-meaning
  names (`second-engine-check`, `warning-reread`, `vlm-assist`,
  `enrichment`) declared as a closed, documented enum; engine
  implementation names stay in logs/telemetry.
- **AD-38: error contract table.** Every new endpoint uses the existing
  `{error, code}` envelope with fix-carrying copy; `expired` ≠
  `not_found`; queue-shed 503 carries `Retry-After`; cancel conflicts
  409; malformed multipart 400 with named code.
- **AD-39: cancel stays internal.** `include_in_schema=False`; the
  cancel token documented in the POST response contract, never in URLs
  or logs; 409 after settle; re-verify remains the only user-facing
  trigger.
- **AD-40: /healthz schema named.** `ready: bool` stays true during
  degraded-paddle (verdicts still served); adds `state:
  "ready"|"degraded_paddle"|"down"`, `queue: {depth, oldest_age_s}`,
  `rss_mb`; asserted by `make smoke`.

## Decision Audit Trail

40 auto-decisions (AD-1..AD-40) documented inline in the phase sections
above, each with rationale. Classification summary: mechanical 39;
taste 1 (**AD-9** — provisional actionability + sign-off gating,
surfaced at the final gate); premise-gate user decisions 5 (D1..D5,
incl. the D2 informed override of both models and D3's silent-degrade
amendment). Principles most exercised: P1 completeness (state machines,
error contracts), P5 explicit-over-clever (admission control over
priority queues, explicit finality field), P3 pragmatic (client-side
gate, poll not SSE).

## Cross-Phase Themes (2+ phases independently)

1. **Trust/audit determinism of mutable verdicts** — CEO (verdict-of-
   record), Design (#4/#10 downgrade arc, sign-off gate), Eng
   (server-side terminality, freeze-vs-merge race), DX (explicit
   finality). Four phases; the highest-confidence signal in the review.
   Resolved coherently: AD-7 + AD-9 + AD-27 + AD-34.
2. **Named orderings without mechanisms** — CEO (AD-3 queue shed), Eng
   (findings 2-4: priority, pools, sidecar). Resolved: AD-21..AD-23.
3. **Silent state change** — Design (#2 batch list, #7 ambiguous
   settle), DX (#1 semantic back-compat). Resolved: AD-11, AD-13,
   AD-15, AD-34.

## GSTACK REVIEW REPORT

| Run | Status | Findings |
|---|---|---|
| CEO (Codex + subagent) | complete | 10 subagent + 6 codex; 6/6 consensus concerns; resolved at premise gate D1-D5 |
| Design (subagent-only; codex sandbox degraded) | complete | 16 (5 critical) → AD-9..AD-19 |
| Eng (subagent + codex-digest) | complete | 20 + codex convergent; 6/6 consensus → AD-20..AD-33 |
| DX (subagent + codex-digest) | complete | 8 + 8 convergent; 6/6 consensus → AD-34..AD-40 |

VERDICT: APPROVED-PENDING-FINAL-GATE (CODEX absorbed via digest where
sandbox blocked file reads; CROSS-MODEL agreement on premises N-P2/N-P4
recorded as informed user override D2 / amendment D3).

**UNRESOLVED DECISIONS:**
- AD-9 (taste): provisional actionability + sign-off gating — default
  ratified (override-freezes-field; sign-off blocked while guard jobs
  pending, explicit confirm escape), user may flip at the final gate.

## NOT in scope

- Removing paddle (rejected by research — it stays as QA + CPU default).
- NIM containers/NVAIE anywhere (open-weights route ratified by the
  economics research).
- Ray/Redis/external queue infra (NVIDIA-scale, not 2-worker scale).
- Sending label images to any cloud API (hard line regardless of N-P4).
- Deployed URL work (separate P1 deliverable, unchanged).

## CEO REVIEW (Phase 1, /autoplan, 2026-08-02)

Mode: SELECTIVE EXPANSION. Approach decision: made by user at premise gate
(D2 — plan as written, nemotron fast path in GPU profile; both-model
challenge overridden). Voices: Codex + Claude subagent, consensus table in
review log; 6/6 dimensions returned CONFIRMED concerns, resolved at the
premise gate (D2-D5).

### 0B What already exists (leverage map)

| Sub-problem | Existing code |
|---|---|
| Engine seam | `api/extractor.py` Extractor protocol + `build_extractor()` |
| GPU sidecar + HTTP wrapper | `docker-compose.gpu.yml`, `scripts/nemotron_server.py` |
| Cross-engine field diff | this session's golden-sweep harness (scratchpad, to be landed as `make eval-compare` seed) |
| Panel merge semantics | `verify_multi` (per-panel; NOT reusable for tier merge — logged eng learning) |
| Warm/health pattern | `PaddleExtractor.warm` + `/healthz` |
| Evidence crops/UI | existing bbox → crop pipeline |
| Job pool | `ThreadPoolExecutor(max_workers=2)` in `api/main.py` (to be wrapped, not replaced) |

### 0C Dream state

```
CURRENT: paddle sync verify 2.9s, single verdict    THIS PLAN: <1s provisional + layered
no jobs, no VLM, engines swap by env       --->     refinement, dual-engine telemetry,   --->
                                                    VLM assist, silent-degrade cloud LLM
12-MONTH IDEAL: full CFR rules engine w/ citations, COLA-form ingestion, deployed,
calibrated per-engine confidence, enrichment layers proven by E4 telemetry data
```
Delta: this plan builds the runtime chassis for the ideal but does not
advance the rules/citations moat (deferred per D4 sequencing).

### 0E Temporal interrogation (resolved now, not "later")

- HOUR 1: verdict-of-record semantics — RESOLVED: sign-off freezes the
  record; later refinements append as annotations, never mutations
  (decision AD-7 below). CSV export exports the frozen record.
- HOUR 2-3: job identity/dedup — jobs keyed `(result_id, layer)`;
  re-verify cancels pending jobs for the old result_id first.
- HOUR 4-5: GPU contention — S1 fast path, J2 crops, J3 VLM share one
  GPU; priority: S1 > J2 > J3; J3 batch size 1; VLM loads lazily and
  only in the A10 profile (laptop profile: J3 remote-dev only).
- HOUR 6+: fixture strategy — recorded engine outputs per golden per
  engine version, committed; live-engine tests marked and skipped in CI.

### Sections 1-11 (findings + auto-decisions AD-n; full depth, condensed prose)

**S1 Architecture.**
```
POST /api/verify ─► S0 intake ─► S1 OCR(primary) ─► S2 verify ─► store[result_id] ─► 202-style response
                                   │ (GPU profile: nemotron via sidecar HTTP)
                                   ▼ sidecar down? → AD-1: degrade to paddle sync path, log, banner
 job queue (bounded 64) ─► J1 paddle QA ─► merge_refinement ─► store update ─► GET /api/verify/{id}
                        ─► J2 crop re-OCR (GPU)                                   │ sign-off freezes (AD-7)
                        ─► J3 VLM (GPU, lazy)          UI poll ◄──────────────────┘
                        ─► J4 Azure LLM (silent no-op offline, D3)
```
Findings→decisions: **AD-1** sidecar-down fallback = paddle sync (explicit
over clever); **AD-2** single in-process store+queue (no Redis; P3/P5) —
restart loses pending refinements: acceptable, provisional verdicts
persist only when signed off; **AD-3** 10x load breaks at GPU lock first
→ priority ordering above + queue shed 503 (already planned). SPOF: GPU
VM in GPU profile — CPU profile unaffected. Rollback: env flip
(`LABELCHECK_EXTRACTOR`, per-layer flags) — minutes, no migrations.

**S2 Error & Rescue Registry.**
```
CODEPATH                  | FAILURE                       | RESCUE                                | USER SEES
NemotronExtractor.extract | URLError/timeout              | AD-1 paddle fallback + retry 1x       | slower verify, banner
                          | 503 warming                   | poll ready ≤300s (exists)             | "warming up"
                          | malformed JSON                | raise → fallback AD-1                 | slower verify
job queue submit          | queue full                    | 503 shed (planned)                    | "busy, retry"
J1 paddle QA              | paddle crash                  | job error state; shadow row 'error'   | nothing (shadow)
J2 crop re-OCR            | crop OOB / empty band         | skip refinement, log                  | field stays provisional-final
J3 VLM call               | OOM on 4GB dev                | profile-gated: never loads locally    | n/a
                          | malformed/refusal response    | discard suggestion, telemetry row     | nothing
J4 Azure LLM              | unreachable/no key/timeout    | SILENT NO-OP (D3), telemetry row      | nothing — byte-identical
                          | malformed/injection output    | schema-validate; discard on fail      | nothing
merge_refinement          | conflicting concurrent update | store lock per result_id              | consistent view
GET /{result_id}          | unknown/expired id            | 404 with "re-verify" hint             | clear error
```
GAPS found and closed: **AD-4** J4 output schema validation (LLM output
never trusted raw); **AD-5** per-result_id store lock.

**S3 Security.** New surface: `GET /api/verify/{id}`, `POST .../cancel`,
outbound Azure call (J4). Findings: result_id guessable → **AD-6**
UUIDv4, loopback-only posture unchanged (auth-less by design, documented).
Cancel endpoint: idempotent, only affects own result_id — no cross-user
concept (single-tenant tool). Azure key: env only, gitignored .env
(pattern exists). **Prompt injection via label text** (OCR text → LLM):
real vector; mitigated by AD-4 schema validation + J4 output labeled
"AI-suggested" + never a verdict source (plan already states) — residual
risk accepted, logged. Audit: refinement provenance rows double as audit
trail; sign-off freeze (AD-7) completes it.

**S4 Data flow & interaction edges.** Double-submit verify → two
result_ids, old jobs cancelled on re-verify (0E). Navigate away →
jobs complete, store TTL reaps (AD: TTL 1h). Job runs twice → keyed
dedup (0E). Queue backs up (batch) → D5 degradation policy (guard-only +
sampled shadow). Results change mid-view → poll sees monotonic
refinement states; frozen after sign-off (AD-7). Zero-word OCR result →
existing NEEDS_REVIEW path unchanged.

**S5 Code quality.** Reuses Extractor protocol; `merge_refinement` is
intentionally separate from `_MERGE_RANK` (not a DRY violation — logged
eng learning mandates separation; comment must say why). Naming: layers
J1-J4 get named constants, not magic strings. Over-engineering check:
SSE deferred (poll only, P5) — **AD-8**. Under-engineering: queue needs
explicit bounded-ness test.

**S6 Test review.** New codepaths → coverage (full table in eng-phase
test plan artifact): engine fallback (unit+integration, fake sidecar),
queue bound/shed (unit), merge_refinement (property tests: no silent
MATCH upgrade from single read; downgrade wins; provenance present),
J1 shadow row schema (unit), J2 crop recovery (fixture: spirits_clean
"drive a car" — regression), J4 silent no-op (integration, no-network
env — MUST run in the no-egress CI job to prove byte-identical), UI
refinement states (JS harness TODO extends). 2am-Friday test: kill
sidecar mid-batch → all verdicts still land via fallback. Chaos: queue
full + sidecar down simultaneously. Flakiness: live-engine tests
excluded from CI (recorded fixtures per 0E).

**S7 Performance.** GPU contention priority (0E). Paddle J1 doubles CPU
per verify → D5 policy caps it. VRAM: laptop 4GB = OCR only (J3 never
loads — profile-gated); A10 24GB = OCR+VLM fits (~20GiB, unverified —
carried risk flag). p99 slow paths: J3 VLM 5-15s (background, fine),
J1 paddle 5s powersave (background), S1 fast path target ≤1s p99 GPU /
≤5s CPU. No DB changes; store is in-memory dict + lock.

**S8 Observability.** Per-job structured logs (result_id, layer, ms,
outcome); E4 telemetry rows (engine pair, field, agree/disagree); queue
depth + oldest-job-age on /healthz; `enrichment_unavailable` counter
(J4); day-1 dashboard = healthz fields; runbook lines per failure mode
in compose header docs. Metric that says "it works": refinement
settle-time p95 and guard-disagreement rate.

**S9 Deployment.** All layers feature-flagged (`LABELCHECK_JOBS`,
per-layer flags); compose profiles unchanged pattern; rollout order:
N1 flags-off → enable per layer; rollback = flag off (minutes); no
migrations; smoke: existing `make smoke` + new `/healthz` queue fields;
no-egress CI job gains J4-silent-no-op assertion (S6).

**S10 Long-term trajectory.** Debt: custom in-process queue (small,
bounded, documented — accepted vs infra dependency); path dependency on
NVIDIA family contained by Extractor seam + JSON job contracts.
Reversibility: 4/5 (flags + env; the 1-way door is the verdict-record
semantics — AD-7 chosen deliberately). 1-year read: plan + research docs
give the why; PLAN-enrichment.md references measurements. Platform
potential: the job/refinement chassis is what the future CFR rules
engine's slow checks (e.g., formula lookups) would ride — genuine
platform win.

**S11 Design/UX (CEO-level).** State coverage: refining badge (loading),
no-jobs (absent), job-error (silent for shadow, badge-error for J2/J3),
settle (success), partial (some layers done). Journey: provisional
verdict must be visually distinct from final (evaluator trust);
guard-disagreement view is the emotionally loaded moment — both reads
side-by-side, no auto-resolution. AI-slop risk: "refining…" language
generic — name the layer ("cross-checking with second engine…").
Deep design review runs as Phase 2.

### NOT in scope
Unchanged from draft + (per gate): permanence of J1 QA (decided at N7),
cloud enrichment beyond silent-degrade J4, SSE push (poll only), Redis/
external queue, engine removal.

### Failure Modes Registry (critical flags)
1. GPU sidecar down → AD-1 fallback — **covered**.
2. Cry-wolf window N3 (user-accepted risk, D2) — mitigations: guard
   both-reads UI, N3 exit criteria (clean-label NEEDS_REVIEW rate ≤
   paddle baseline; 3/3 determinism) — **monitored, not eliminated**.
3. Queue backlog under batch → D5 policy — **covered**.
4. J4 injection/malformed → AD-4 — **covered**.
5. Verdict mutation after sign-off → AD-7 freeze — **covered**.
6. VRAM overcommit on A10 (OCR+VLM co-residency unverified) — flagged
   to eng phase — **open, carried**.

## ENG REVIEW (Phase 3, /autoplan, 2026-08-02) — voices: Claude subagent (file-grounded, 20 findings) + Codex (inline digest; sandbox can't read files)

ENG CONSENSUS: 1. Architecture sound? Claude NO / Codex NO → **CONFIRMED
gap** (mechanisms missing; fixed below). 2. Tests sufficient? both NO →
**CONFIRMED** (expanded below). 3. Performance? both partial →
**CONFIRMED** (pools/OOM fixed below). 4. Security? both mostly-with-adds
→ **CONFIRMED**. 5. Error paths? both partial (terminality) →
**CONFIRMED**. 6. Deployment risk? both manageable-with-invariants →
**CONFIRMED**.

Auto-decisions AD-20..AD-33 (eng tiebreak P5 explicit + P3 pragmatic):

- **AD-20 (fixes the critical self-contradiction): per-layer agreement
  semantics for merge_refinement.** J2 crop re-OCR counts as an
  authoritative single read for statutory-text upgrades WHEN J1 guard
  concurs on that field; everywhere else MATCH upgrades need two
  independent agreeing reads. S1's own failed read never counts as an
  agreeing read. Status lattice is the FULL set (incl. NOT_REQUIRED /
  NOT_CHECKED): a layer discovering previously-unfound text applies
  immediately (like a downgrade — it can create a MISMATCH); property
  tests enumerate the lattice, not the 3-state triangle.
- **AD-21: N1 extends to the sidecar.** Inference moves to a worker
  thread with an internal queue; /v1/health/ready stays on a free event
  loop; 429/503 with queue depth when saturated. (The sidecar today has
  the same sync-in-async bug N1 fixes in the API.)
- **AD-22: GPU priority mechanism = client-side admission control.** The
  API holds a GPU-work gate: J2/J3 dispatch is deferred while any S1
  call is in flight or queued. No sidecar priority queue (explicit over
  clever).
- **AD-23: separate executors.** Fast-path pool (sized to engine
  concurrency) + background job pool; N1 documents the arithmetic:
  paddle's lock makes J1 serial (~0.2-0.35 verifies/s ceiling — written
  next to D5's sampling rate); queue bound vs drain vs shed rate at 300
  labels stated, not implied.
- **AD-24: AD-1 fallback preconditions become plan text.** GPU profile
  warms BOTH engines at startup (paddle models baked in the image);
  /healthz goes tri-state ready/degraded-paddle/down; J1 auto-suspends
  while AD-1 active (shared PaddleExtractor); RAM budget: paddle RSS +
  decode buffers exceed the current `mem_limit: 4g` under batch — limit
  raised and RSS exposed on /healthz.
- **AD-25: single-process invariant asserted** (`workers == 1` at
  startup; store correctness depends on it; --reload noted dev-only).
- **AD-26: sidecar circuit breaker.** N consecutive failures → GPU-layer
  jobs fail-fast to settled-skipped until a probe succeeds; extract
  timeout drops 60s → 10s.
- **AD-27: terminality is server-side.** Job watchdog forces `timed_out`
  / `lost` at deadline; late completions hit a tombstone check inside
  the store lock and are rejected (or annotation-only); every enqueued
  job writes exactly one terminal state including exception paths
  (injected-exception test); durations use monotonic time. POST response
  marks layers `shed` at submit time when the queue refuses them.
- **AD-28: TTL is idle-based**; signed-off results persist through the
  session store before reap; `request_id`/`result_id` frozen at S2 and
  threaded through revisions.
- **AD-29: per-engine CONF_FLOOR lands at N3** (crude constants from the
  existing golden sweep), refined at N7 — the interim window must not
  run paddle-tuned thresholds against nemotron confidences.
- **AD-30: guard compares normalized text only** (loose/whitespace_only
  pipeline), never box-derived quantities — paddle's synthetic word
  boxes vs nemotron's true boxes would otherwise inflate disagreement
  telemetry. Fixture: identical reads, different geometry → guard
  agrees.
- **AD-31: security hardening.** Strict Host validation + content-type
  enforcement + startup refusal when binding non-loopback without auth;
  result endpoints inherit the deployed-URL work's auth and are blocked
  from deploy until it exists; cancel requires the token returned by
  the original POST; J4 prompt hygiene: OCR text delimited as untrusted
  data, one label per call (no prompt batching), exact outbound payload
  logged (proves images never sent), drafts rendered beside quoted
  source text.
- **AD-32: revision increments on EVERY store mutation** including
  job-state transitions; merge_refinement preserves field order across
  revisions.
- **AD-33: test plan expanded** — artifact on disk; top of the list is
  the hung-engine wedge (native call holding the extractor lock forever:
  watchdog marks engine wedged → AD-1 degrade; /healthz must not report
  ready while wedged).

## Test plan (ratified by eng review; artifact copy on disk)

- N1 foundation: event-loop liveness (healthz under concurrent 40 MP
  verify); queue-full 503; **hung-engine wedge + watchdog recovery**;
  injected-exception → exactly-one-terminal-state; TTL idle-reset +
  reap-during-merge race; cancel idempotency + late-completion
  tombstone; workers==1 assertion; monotonic-clock TTLs.
- N3: golden sweep per engine + merged; guard statutory-disagreement
  fixture; geometry-differs-guard-agrees fixture (AD-30); shadow row
  schema; per-engine CONF_FLOOR smoke (AD-29); fast-path latency under
  full job queue (starvation regression); 30-label CI-scale soak;
  sidecar-death mid-batch (circuit-breaker fail-fast); AD-1 active →
  J1 suspended assertion; freeze-vs-merge transactional race (agent
  decision vs concurrent J1 downgrade); server-side revision
  monotonicity under racing merges.
- N4: 8 regressing goldens as acceptance fixtures; spirits_clean
  "drive a car" regression; **evidence-coordinate round-trip** (crop
  space → panel space → original bitmap); AD-20 property fixtures
  (S1 fail + J2 MATCH + J1 concur → upgrade; J1 shed → stays
  provisional).
- Merge: property tests over the FULL status lattice (AD-20); never a
  silent MATCH upgrade from a single non-privileged read; downgrade
  always wins; discovery applies immediately; provenance always present.
- J4: recorded-response fixtures; schema-valid-but-hostile output
  fixture; silent no-op proven byte-identical in the no-egress CI job;
  injection fixture (label text containing instruction-like content →
  draft renders it quoted, never executed).
- Chaos: queue full + sidecar down + AD-1 active simultaneously; fault
  injection (kill sidecar, kill API mid-job, delayed completion after
  cancel) — not mocks only.
- VLM/LLM layers: recorded-response fixtures; no live calls in CI;
  corrupted/oversized image fixtures on the upload path.
