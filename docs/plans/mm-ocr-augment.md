<!-- /autoplan restore point: /home/niccolox/.gstack/projects/niccolox-treasury-instructions/main-autoplan-restore-20260804-230112.md -->
# Plan: Nemotron + OpenAI document intelligence solution (minimal increments)

Status: APPROVED (2026-08-05) — /autoplan-reviewed: 3 phases, 6 model voices,
37 amendments folded, final gate approved as-is. D-0 is a stop-gate.
Scope directive from the user: use the existing implementation; minimal
incremental changes; NOT a massive refactor.
Research grounding: docs/research/document-intelligence-pipeline-nemotron-openai.md.

## The solution, stated whole

Label Check IS already a document intelligence pipeline: Nemotron OCR v2
grounds (words + boxes, S1), the rules engine judges (S2), background
layers refine (J1 paddle QA, J2 crop re-OCR, J3 VLM assist), and OpenAI
text layers reason over structured results (ai_review triage, PASS/FAIL
summaries — both shipped). The missing piece is the **multimodal second
read**: an OpenAI-compatible model that re-reads a troubled crop in
transcription mode, judged deterministically. Division of labor per the
research: OCR grounds, multimodal transcribes, the rules engine judges —
no model output ever mutates a field status.

## D-0 · Value gate FIRST (new — from cross-model review, ~2 hours)

Before any client code: measure on the golden + COLA Cloud corpora how
many fields settle MISMATCH/NEEDS_REVIEW after J2 (the only rows the
layer can touch), bucketed by reason code. Ship gate for everything
below: if troubled-field incidence is negligible, or the failure
taxonomy says the errors are crop-selection/rule-interpretation (not
transcription), STOP and re-plan — a second reader can't help those.
Output: a table in this plan (incidence, reason buckets, expected
mm-read fire rate).

### D-0 RESULTS (measured 2026-08-05 — api/eval/measure_troubled.py, GATE: PASS)

134 apps (golden 15 + COLA Cloud 119) through the full live pipeline
(Nemotron S1 → rules S2 → J1/J2 settle). 213 troubled fields total.

| Corpus | Apps | Troubled | Eligible today (NR∧bbox) | Widened (MM∧bbox) | Unreachable (no bbox) | Fire/app today→widened |
|---|---|---|---|---|---|---|
| golden | 15 | 9 | 3 | 3 | 3 | 0.20→0.40 |
| colacloud/beer | 26 | 66 | 17 | 13 | 36 | 0.65→1.15 |
| colacloud/champagne | 20 | 15 | 4 | 5 | 6 | 0.20→0.45 |
| colacloud/imported_wine | 22 | 33 | 7 | 8 | 18 | 0.32→0.68 |
| colacloud/kentucky_whisky | 4 | 9 | 5 | 1 | 3 | 1.25→1.50 |
| colacloud/napa_zinfandel | 8 | 17 | 8 | 2 | 7 | 1.00→1.25 |
| colacloud/spirits | 15 | 27 | 11 | 4 | 12 | 0.73→1.00 |
| colacloud/wine | 24 | 37 | 9 | 5 | 23 | 0.38→0.58 |
| **TOTAL** | **134** | **213** | **64** | **41** | **108** | **0.48→0.78** |

Reason codes — eligible today: unreadable 23, engine_disagreement 15,
possible_ocr_misread 10, weight_contrast_suspect 9, format_nonstandard 5,
ambiguous 2. Widened: statutory_text_differs 24, value_differs 14,
weight_contrast_violation 3. Unreachable: not_found/not_visible 107,
misc 1.

**Gate verdict — BUILD PROCEEDS, with three data-backed conclusions:**
1. **Incidence is real**: 105 crop-reachable troubled fields; 80 of 134
   apps (60%) fire ≥1 second read under the widened rule (0.78/app).
2. **The reads are helpable**: 75% of today's eligible rows and 93% of
   widened rows carry transcription-class reason codes (unreadable,
   engine_disagreement, possible_ocr_misread, statutory_text_differs,
   value_differs). The typography/format rows (17) are correctly
   excluded by the judge's narrowed-verdict design (amendment 21).
3. **Amendment 17 (MISMATCH widening) is validated**: it adds 41 rows at
   the HIGHEST helpable ratio — the sides_with_application population.
   Cap displacement = 0: J3_MAX_FIELDS=3 never binds; no cap change needed.
   Structural limit confirmed: 51% of troubled rows have no bbox and are
   unreachable by ANY crop reader — that remains locate-layer work
   (TODOS: warning best-candidate-wins), not mm-read scope.

Raw data: api/eval/results/d0-troubled-incidence.json.

## Deltas (each small, each independently shippable)

### D-1 · `transcribe_crop()` on the existing VLM client (~half day)

`api/vlm.py` grows one method beside `read_crop()`: transcription mode
("transcribe every word in this image verbatim; output text only").
Same crop budget (180 KB) and silent-None posture, with four deltas
from review findings:
- **Mode-specific token cap** (~600, not read_crop's 160 — the
  statutory warning alone is ~45 words); `finish_reason=length` ⇒
  `error`, never a judged transcription.
- **`error` ≠ `unreadable`**: breaker-open / transport / truncation /
  schema drift report `error` (with cause in debug); `unreadable` is
  reserved for a model that answered "can't read this".
- **Per-mode breaker keys** — transcription failures must not cool off
  the shipped question-mode assist.
- **Engine label derived from the client** (fixes the existing
  hardcoded "nano-vl-8b" provenance at layers.py:309/322).

### D-2 · mistral_doc — POST-PROBE DECISION GATE (was: a dialect)

Cross-model agreement: the Mistral OCR API (document in, markdown pages
+ boxes + confidence out) is a different request/response contract, not
a third chat dialect — "no new client" was wrong. D-2 is now: probe the
deployment's wire format (~1 hour), then DECIDE with real information —
implement as its own small client, or skip in favor of GPT-4.1 vision.
Considered alternative, recorded: Azure Document Intelligence Read
($1.50/1k pages, US-origin, managed) — deferred because it adds a
fourth external service class and a non-OpenAI-compatible contract;
revisit if the probe kills mistral_doc AND GPT-4.1 vision stays
undeployed.

**D-2 PROBE RESULT (2026-08-05) — DECIDED: IMPLEMENTED.** Deployment
`mistral-document-ai-2512` answers at
`https://niccolox-6191-resource.services.ai.azure.com/providers/mistral/azure/ocr`
(Bearer auth, existing resource key). Wire: `{"model", "document":
{type: image_url, image_url: data-url}}` → `{pages: [{markdown, ...}]}`.
Transcription quality on the golden: full label read perfectly at 600 px,
statutory warning verbatim. Caveat vs the research: word-level boxes are
NOT in this response shape (block markdown only) — irrelevant to the mm
layer, which judges text. Implemented as a transcription-only provider
branch in the SAME transcribe_crop (question mode gated off — an OCR API
has no chat dialect). Live crop→transcribe→judge chain verified: warning
band crop → 357-char transcription → judge → agrees.

### D-3 · Transcribe-then-judge in run_j3 (~half day)

When transcription mode is enabled, it **replaces** question mode for
that field (one model call per field — the "rides J3" latency story is
only honest this way; a failed transcribe falls back to question mode
ONCE, both calls never run on success). The judge is NOT "the same
compare S2 uses" (review finding: S2 compares operate on located,
box-anchored input) — it is a set of small **per-field adapters**:
normalized containment search for the expected application value inside
the transcription, reusing the existing pure helpers in `api/rules/*`
(ABV tolerance parse, statutory-warning normalize, net-contents
grammar). Attach as the existing suggestion contract:
`mm_reread: {text, verdict: agrees|sides_with_application|differs|
unreadable|error, model, elapsed_ms}` — suggestion-only, no merge
changes, extends `test_j3_attaches_suggestion_without_status_change`.

**Asymmetric verdict semantics** (both voices): the second reader is
statistically WEAKER than Nemotron on exact text, so raw disagreement
is noise. `agrees` = confirmation chip. `sides_with_application` (the
transcription matches the applicant's value against OCR) = the one
genuinely actionable disagreement — amber emphasis. Plain `differs`
renders in the debug block only, never as a headline chip.

### D-4 · Row chip + debug block (~half day)

UI: "Second read: agrees / sides with application — <excerpt>" chip on
troubled rows, ai_review-card debug pattern (provider, model, elapsed,
verdict path, error cause). Null-guarded for restored sessions. Ships
only after D-5's precision floor passes (below).

### D-5 · Evals, traps, and the ship gate (~half day)

- Fast tier: canned transcriptions through the judge adapters (ABV
  tolerance, warning normalize incl. truncated-crop cases, net
  contents; brand REMOVED from scope — no identified failure mode).
- **Keyless demo path** (review: the feature must be visible to an
  evaluator with zero credentials): a fixture provider
  (`LABELCHECK_VLM_PROVIDER=fixture` — a value of the ONE provider
  knob; read_crop returns None under it, documented) drives canned
  transcriptions keyed by (sample, field) — never crop bytes —
  end-to-end into the D-4 chip on a NAMED training sample.
- Injection trap: adversarial crop text (instruction strings, and the
  subtler omission/normalization attacks) — transcription fidelity
  asserted, judge decides.
- Live tier (`LABELCHECK_MM_EVAL=1`): golden crops through the real
  provider; **ship gate: disagreement precision ≥ threshold set at D-0
  (proposal: ≥80% of `sides_with_application` verdicts correct on
  goldens) before D-4 defaults on anywhere.**

### D-5 PRECISION GATE RESULT (measured live 2026-08-05 — GATE: PASS)

Provider: mistral_doc (mistral-document-ai-2512) over all 134 corpus
apps. 105 second reads fired; verdicts: agrees 52, sides_with_application
21, differs 29 (debug-only), unreadable 0, error 3.
**sides_with_application precision: 21/21 = 100%** (floor 80%, min n 10)
→ D-4 may default on. Honest caveat: 20 of the 21 positives are
calibration-tier (approved COLA labels, correct by construction); the
held-out golden traps contributed n=1 (trap_titlecase_warning — content
words present, typography wrong — judged correctly, exactly the designed
narrowed-verdict case). Raw data: api/eval/results/mm-precision.json.

### D-6 · Operator docs (~1 hour)

Extend docs/enable-azure-vlm.md: provider matrix, flag semantics
(below), GPT-4.1 Gov note **marked conditional — Gov vision-input
parity is unverified** (research's open item), and the keyless demo.

## Flag semantics (corrected — review caught the code reality)

`LABELCHECK_VLM_PROVIDER` unset ⇒ `nvidia` (shipped J3 behavior,
unchanged). The NEW transcription path requires its own flag,
**`LABELCHECK_MM_READ`, default off** — so "byte-identical when unset"
is true without silently changing J3, and an ambient NVIDIA_API_KEY
cannot activate the new egress path. D3 semantics: `MM_READ` off or
provider/key absent → zero egress from this layer, byte-identical
results (extends the no-egress suite with both cases separately).

## Model placement (from the research, binding here)

- Working today: `mistral_doc` (grounded; $4/1k pages) — pending D-2 probe.
- Practical unlock: deploy **GPT-4.1 vision** on niccolox-6191 —
  Gov-parity model CLASS (vision-input parity in Gov unverified).
- Never: Kimi-K2.6 (text-only; measured 53 s reasoning burn). PRC-origin
  models excluded from image paths per the repo's documented supply-chain
  posture (SBOM annotations, PLAN-us-stack) — policy reference, not ad-hoc.

## Invariants (test plan)

1. `MM_READ` off / provider or key absent → byte-identical results,
   zero egress (both cases tested separately).
2. Suggestion-only: mm_reread never changes a field status.
3. Crops only: a full label never leaves the process.
4. Deterministic judge: same transcription in → same verdict out.
5. Injection trap: adversarial crop text never alters any verdict.
6. Breaker: per-mode; transcription failures never cool off question mode.
7. Latency: transcription replaces (not adds to) the per-field J3 call;
   J3 deadline unchanged; provisional path untouched.
8. Truncation: `finish_reason=length` or crop-boundary suspicion ⇒
   `error`, never a judged `differs`.

## NOT in scope (per the minimal-increment directive)

- No new JobQueue layers, no merge-layer changes, no engine swaps.
- No COLA-form ingestion (VLM-as-structurer) — TODOS.md P2 (both review
  voices flag it as the strategically larger delta; see User Challenge
  at the approval gate).
- No Nemotron Parse layout layer — TODOS.md candidate.
- No Azure Document Intelligence integration — recorded alternative in D-2.
- No RAG/embedding/knowledge-graph machinery.

## What already exists (leverage map)

| Sub-problem | Existing code | Reused? |
|---|---|---|
| Multimodal client, dialects, breaker, crop budget | api/vlm.py | Yes (D-1 extends) |
| Troubled-field selection + crop plumbing + suggestion merge | api/layers.py run_j3 | Yes (D-3 rides it) |
| Pure field-compare helpers | api/rules/{abv,warning,malt,wine}.py | Yes (judge adapters) |
| Debug-visible AI card pattern | app.js ai_review card | Yes (D-4 copies) |
| Golden eval harness + live-tier flag pattern | api/tests, api/eval | Yes (D-5 extends) |
| No-egress + suggestion-only invariant tests | test suite | Yes (extended) |

## Dream state delta

CURRENT: grounded OCR + deterministic rules + prose-only VLM suggestions
+ text triage/summaries → THIS PLAN: adds a verifiable second read with
asymmetric, evidence-anchored verdicts → 12-MONTH IDEAL: COLA-form
ingestion (structurer), 27 CFR citation rules engine, Gov deployment.
The plan moves toward the ideal without new machinery; the largest
remaining gap (application-side ingestion) is deliberately NOT this plan.

## Effort

D-0 first (~2 h). Then ~2 days human-scale / half day CC-scale total:
D-1 → D-3 → D-5 as the smallest honest unit; D-2 probe anytime; D-4
gated on D-5's precision floor; D-6 trailing.

---

# /autoplan Phase 1 — CEO review record (2026-08-04)

## CEO DUAL VOICES — CONSENSUS TABLE
```
  Dimension                             Claude   Codex    Consensus
  ────────────────────────────────────  ───────  ───────  ─────────
  1. Premises valid?                    NO (4    NO (2    CONFIRMED-CONCERN →
                                        asserted) asserted) D-0 value gate added
  2. Right problem to solve?            QUESTIONED QUESTIONED CONFIRMED → USER
                                        (F9)     (#2,#20)  CHALLENGE at gate
  3. Scope calibration correct?         D-2 wrong D-2 wrong CONFIRMED → D-2
                                                            demoted to probe gate
  4. Alternatives sufficiently explored? NO (Azure NO (J2-  CONFIRMED-CONCERN →
                                        DI, F8)  improve,#5) alternatives recorded
  5. Competitive/market risks covered?  PARTIAL  PARTIAL   CONFIRMED-CONCERN
                                        (ACU)    (#18)     (noted, non-blocking)
  6. 6-month trajectory sound?          YES w/   Shelfware  PARTIAL → keyless
                                        fixes    risk (#6)  demo path added
```
Voices: Claude subagent 12 findings (F1–F12) · Codex 20 findings (#1–#20).
Codex #7 (provider default is nvidia, not off) VERIFIED true against
vlm.py:45 → fixed via the separate LABELCHECK_MM_READ flag.

## Step 0 record
- 0A premises: P-A "a verifiable second read adds screening value" —
  now EVIDENCE-GATED by D-0 (was asserted). P-B "extend existing seams,
  no refactor" — confirmed by leverage map. P-C "mistral_doc worth a
  dialect" — demoted to post-probe decision. P-D "GPT-4.1 = Gov parity"
  — marked conditional (vision parity unverified).
- 0C-bis alternatives: A minimal seam extension (CHOSEN — P3/P5 + user
  directive); B new J-mm JobQueue layer (rejected: duplicates J3 crop
  plumbing, more revision churn); C unified multimodal client refactor
  (rejected: violates the binding no-refactor directive).
- 0D SELECTIVE EXPANSION, minimal baseline held. Expansion candidates
  → all DEFERRED per user directive: E4 agree/disagree telemetry (S),
  GPT-4.1 deploy + A/B eval (S, user-side), rotated-crop retry (M,
  existing TODO), COLA-form ingestion (M, existing TODO P2).
- 0E resolved-now decisions: field eligibility = J3's existing flagged
  set; judge = adapters over api/rules pure helpers; mistral mapping
  decided post-probe; canned-fixture provider for evals and demo.

## Sections 1–11 (findings and dispositions)
1. **Architecture** — no new components; new coupling: run_j3 → rules
   helpers (already transitively present via verify). Diagram: research
   doc Part 3 (current, includes this layer). Failure scenario: dead
   provider → per-mode breaker → question-mode fallback unaffected.
   Rollback: unset MM_READ. Finding: latency double-call → fixed
   (replace, not add). 1 issue, resolved in-plan.
2. **Error & rescue** — registry below; GAP found (judge exception
   unspecified) → fixed: per-field try/except, `error` verdict, logged.
3. **Security** — new egress path flag-gated (MM_READ default off);
   crops-only; injection via transcribe-verbatim + deterministic judge
   + trap corpus incl. omission attacks; secrets in env; no new
   endpoints. Data governance: pre-approval images sensitive → flag
   stays off in stage/prod until the placement standard clears (matches
   azure-enrichment-layers policy). 0 open issues.
4. **Data flow & edge cases** — shadow paths per registry; UI: chip
   null-guarded for restored sessions; stale-result compat = absent key
   renders nothing. 0 open issues after D-1 error taxonomy.
5. **Code quality** — DRY held (adapters reuse rules helpers; no
   parallel client for chat providers); brand adapter cut (no failure
   mode — Codex #17). 1 issue, resolved by scope cut.
6. **Tests** — new codepaths all enumerated in D-5 (+judge-exception,
   +truncation, +both flag-absence cases). 2 a.m. test: fixture
   provider e2e into the chip. Hostile test: truncated warning crop
   must yield error, not differs. Chaos: breaker trip mid-batch leaves
   question mode alive. LLM change ⇒ golden eval suites named in D-5.
7. **Performance** — one HTTP call per troubled field (replaces, not
   adds); ≤180 KB crops; no DB/index impact; J3 deadline unchanged.
   No issues.
8. **Observability** — verdict + cause in debug block, log lines on
   transcribe/judge, engine label fixed (was hardcoded). Telemetry
   expansion deferred (E4 candidate). No blocking issues.
9. **Deployment** — no migrations; two independent flags; rollback =
   env change; no-egress CI proof extended. No issues.
10. **Trajectory** — reversibility 5/5; debt: possible mistral client
    (post-probe, contained); docs in D-6. The 1-year reader sees one
    method + adapters, not a framework. No issues.
11. **Design/UX** — chip states: agrees / sides-with-application /
    (debug-only differs / error); no loading state needed (rides settle
    refresh); a11y follows existing chip patterns. No issues.

## Error & Rescue Registry (new codepaths)
```
CODEPATH                     FAILURE                    CLASS/SIGNAL      RESCUED → USER SEES
transcribe_crop HTTP         timeout/refused/DNS        URLError/OSError  Y → error verdict; breaker counts; chip absent
transcribe_crop parse        malformed body             KeyError/JSONDec  Y → error verdict (cause=schema)
transcribe_crop truncation   finish_reason=length       explicit check    Y → error verdict (cause=truncated)
model refusal/empty          empty content              explicit check    Y → unreadable; question-mode fallback once
judge adapter                unexpected exception       per-field except  Y → error verdict, logged with field+rid
oversized crop               >180 KB                    size check        Y → skip silently (existing posture)
breaker open                 3 fails/30 s, per-mode     state check       Y → skip; question mode unaffected
```
CRITICAL GAPS: 0 (all rows rescued, visible in debug, logged).

## Failure Modes Registry
```
CODEPATH        FAILURE MODE          RESCUED  TEST  USER SEES        LOGGED
transcribe      provider dead          Y        Y     no chip          Y
judge           false differs (trunc)  Y        Y     never headlined  Y
chip render     legacy result          Y        Y     nothing          n/a
flags           ambient NVIDIA key     Y        Y     nothing (off)    n/a
```

## Decision Audit Trail
| # | Phase | Decision | Class | Principle | Rationale | Rejected |
|---|---|---|---|---|---|---|
| 1 | CEO | Mode: SELECTIVE EXPANSION, minimal baseline held | Mechanical | autoplan override + user directive | expansions surface as deferrals only | EXPANSION |
| 2 | CEO | Approach A (seam extension) | Mechanical | P3,P5 | B duplicates J3 plumbing; C is the forbidden refactor | B, C |
| 3 | CEO | D-2 demoted to post-probe decision gate | Taste→resolved | P4,P6 | cross-model: different wire contract ≠ dialect | "dialect" framing |
| 4 | CEO | Transcribe REPLACES question mode per field | Mechanical | P5 | makes invariant 7 true instead of aspirational | dual-call |
| 5 | CEO | Mode-specific token cap + length⇒error | Mechanical | P1 | 160 tokens truncates the statutory warning | reuse 160 |
| 6 | CEO | Judge = per-field adapters, not "same compare" | Mechanical | P5 | S2 compares need boxes; free text needs containment | naive reuse |
| 7 | CEO | Per-mode breaker keys | Mechanical | P1 | new path must not cool off shipped assist | shared breaker |
| 8 | CEO | error ≠ unreadable; cause in debug | Mechanical | P1 | provider regressions vs hard crops distinguishable | single bucket |
| 9 | CEO | Asymmetric verdicts; differs = debug-only | Taste (surfaced at gate) | P1 | weaker reader ⇒ raw disagreement is noise | symmetric chips |
| 10 | CEO | LABELCHECK_MM_READ separate flag, default off | Mechanical | P1 | vlm provider defaults nvidia; ambient-key egress risk | flip provider default |
| 11 | CEO | Keyless fixture provider + demo path | Mechanical | P1,P6 | feature must be visible to a zero-credential evaluator | live-only |
| 12 | CEO | D-0 value gate + D-5 precision ship-gate | Mechanical | P1 | both voices: value asserted, not measured | ship blind |
| 13 | CEO | Brand adapter cut from D-5 | Mechanical | P3 | no identified failure mode (Codex #17) | keep |
| 14 | CEO | Azure DI recorded as considered alternative | Mechanical | P6 | omission was a visible hole (F8) | silence |
| 15 | CEO | Expansion candidates all deferred | Mechanical | user directive | minimal-increment is binding | auto-approve S items |
```

---

# /autoplan Phase 3 — Eng review record (2026-08-05)

## ENG DUAL VOICES — CONSENSUS TABLE
```
  Dimension                       Claude subagent        Codex              Consensus
  ──────────────────────────────  ─────────────────────  ─────────────────  ─────────
  1. Architecture sound?          YES, 3 unwired         Same 3 (#1,#2,#3   CONFIRMED w/
                                  decisions (F1,F2,F4)   critical)          amendments
  2. Test coverage sufficient?    NO — 6 gaps (F9)       NO (#5,#14,#15,17) CONFIRMED → D-5+
  3. Performance risks addressed? Deadline math (F2)     #2,#10,#11         CONFIRMED → fixed
  4. Security threats covered?    Chip escaping, fixture Hostile text #17,  CONFIRMED → fixed
                                  spoof (F9a,F10)        fixture #12
  5. Error paths handled?         Taxonomy+churn (F6,F7) #13 constrained    CONFIRMED → fixed
                                  late-mutate (F3)       contract, #3
  6. Deployment risk manageable?  YES w/ flag wording    YES w/ #12         CONFIRMED
                                  fix (F11)
```
Claude subagent: 12 findings (E-F1..E-F12, code-cited). Codex: 18 (#1–#18).
Cross-model confirmations: eligibility population, fallback deadline math,
late mutation post-settle, breaker races, two-submission-site parity,
warning typography not attestable by transcription, ABV cross-layer deps,
verdict three-way underspecification, fixture spoof risk, hostile text.

## Step 0 scope challenge (against real code)
- VLM_QUESTIONS are ALREADY transcription-shaped (layers.py:249–258) —
  D-1's true delta is the token cap + taxonomy, D-3's is the judge.
- run_j3 targets NEEDS_REVIEW∧bbox only, cap 3 (layers.py:280–283) —
  MISMATCH rows and bbox-less NOT_FOUND rows are untouched today.
- TWO J3 submission sites: layers.py:243–246 (J1 chain) and 424–426
  (J2 chain), both deadline_s=45. Gating must live INSIDE run_j3.
- Complexity check: 5 files touched, 0 new classes (fixture provider is
  a branch, mistral client only post-probe) — under the 8-file smell line.
- TODOS cross-ref: rides "Optional VLM assist" (P3) and constrains
  "VLM assist candidate order"; blocks nothing.

## AMENDMENTS (auto-decided, all folded into the deltas above)
| # | Amendment | Source |
|---|---|---|
| 16 | D-0 measures the TRUE eligible set — NEEDS_REVIEW∧bbox and MISMATCH∧bbox separately, no-bbox rows counted as unreachable, J3_MAX_FIELDS=3 cap displacement modeled, both submission sites | E-F1, C#1,#11 |
| 17 | D-3 widens targets to MISMATCH∧bbox rows ONLY when MM_READ=on (that's where sides_with_application lives); selection unchanged when off | E-F1, C#1 |
| 18 | Deadline budget: transcription per-call timeout 12 s; question-mode fallback fires only if ≥20 s of the 45 s job budget remains; never two 30 s calls | E-F2, C#2,#10 |
| 19 | Late-mutation guard: apply closure no-ops when the vlm-assist job is terminal-and-not-DONE; regression test | E-F3, C#3 |
| 20 | available() = union across modes at both chain sites; per-mode check inside run_j3; read_crop path byte-identical (per-mode breaker dict, legacy key preserved, threading.Lock) | E-F4,F7,F8, C#4 |
| 21 | Judge spec = three-way table per adapter: agrees (transcription consistent with OCR read), sides_with_application (normalized app value found in transcription AND S2 said MISMATCH), differs (neither; debug-only). Warning adapter = content-words containment ONLY — prefix typography and weight contrast NOT assessable, verdict explicitly narrowed. ABV adapter passes app_percent + BevType via the same derivation S2 uses; WITHIN_TOLERANCE ⇒ agrees | E-F5, C#6,#7,#8 |
| 22 | Constrained response contract: unreadable ONLY on empty/whitespace or explicit refusal-marker list; all other text is judged | C#13 |
| 23 | error verdict stored at most once per field per run (single apply, no revision churn); cause in debug + job error field | E-F6 |
| 24 | Crop-boundary suspicion = deterministic: bbox touches panel edge OR transcription starts/ends mid-statutory-fragment ⇒ error(crop_boundary) | C#9 |
| 25 | Precision ship-gate hardened: n≥10 sides_with_application samples minimum, calibration (D-0 corpus) vs held-out (goldens) split, coverage reported alongside precision | C#14,#15 |
| 26 | Fixture provider answers only crop-hashes in its canned map (None otherwise); chip carries provider label when provider=fixture | E-F10, C#12 |
| 27 | Flag wording fixed: MM_READ off ⇒ no TRANSCRIPTION egress + byte-identical vs today's J3; key-absent ⇒ zero egress entirely (two separate tests) | E-F11 |
| 28 | mm_reread is a sibling of f["vlm"] + refinements annotation kind="mm-reread"; absent key = legacy result (renderer null-guard) | C#16 |
| 29 | Chip text: esc() + 120-char excerpt cap + control-char strip (test-pinned) | E-F9a, C#17 |
| 30 | D-5 adds: post-budget crop quality eval (JPEG q85 warning band), fallback-exactly-once, eligibility pins, late-timeout mutate, both-breakers-open, slow-provider deadline | E-F9, C#18 |
| 31 | Line refs corrected: engine label layers.py:310/322; submission sites 243–246 and 424–426 | E-F12 |

## Test coverage diagram (Section 3)
```
CODE PATHS                                          USER FLOWS
[+] api/vlm.py transcribe_crop()                    [+] Troubled-row second read
  ├── [GAP→D-5] happy transcription                   ├── [GAP→D-5] chip renders agrees
  ├── [GAP→D-5] timeout / refused (error)             ├── [GAP→D-5] sides_with_application amber
  ├── [GAP→D-5] finish_reason=length (error)          ├── [GAP→D-5] differs stays debug-only
  ├── [GAP→D-5] empty/refusal (unreadable)            ├── [GAP→D-5] legacy result: no chip
  ├── [GAP→D-5] per-mode breaker isolation            └── [GAP→D-5] hostile text escaped
  └── [GAP→D-5] read_crop path byte-identical      [+] Operator flows
[+] api/layers.py run_j3 (amended)                    ├── [GAP→D-5] MM_READ off ⇒ no transcription
  ├── [GAP→D-5] eligibility incl. MISMATCH∧bbox       ├── [GAP→D-5] key absent ⇒ zero egress
  ├── [GAP→D-5] cap displacement                      └── [GAP→D-5] fixture keyless demo e2e
  ├── [GAP→D-5] budget-gated fallback (once)       [→EVAL] live tier: golden crops through
  ├── [GAP→D-5] late-timeout mutate no-op                    provider; precision gate n≥10
  └── [GAP→D-5] judge adapters 3-way verdicts
COVERAGE (pre-implementation): 0/20 — all enumerated as plan requirements.
REGRESSION RULE: read_crop byte-identical + no-egress + suggestion-only
tests are CRITICAL (existing behavior the diff touches).
```

## Failure modes (new codepaths)
```
CODEPATH             FAILURE                 TEST  HANDLED  USER SEES
transcribe timeout   slow provider           Y     Y        no chip; debug cause
late J3 completion   mutate after settle     Y     Y(19)    nothing (guarded)
judge on truncation  false differs           Y     Y(24)    never headlined
breaker cross-talk   transcribe kills Q-mode Y     Y(20)    question mode alive
fixture in prod      fabricated chips        Y     Y(26)    provider-labeled chip
```
CRITICAL GAPS: 0 after amendments.

## Parallelization
Lane A: D-1 vlm.py → D-3 layers.py (sequential, shared contract).
Lane B: D-0 eval script (independent — RUN FIRST as the gate).
Lane C: D-2 probe (independent). Lane D: D-4 UI after A. D-6 docs last.
Conflict: none (disjoint modules per lane).

---

# /autoplan Phase 3.5 — DX review record (2026-08-05)

## DX DUAL VOICES — CONSENSUS TABLE
```
  Dimension                        Claude subagent      Codex           Consensus
  ───────────────────────────────  ───────────────────  ──────────────  ─────────
  1. Getting started < 5 min?      NO — no command,     BLOCKER #1      CONFIRMED → 33
                                   unstable fixture key
  2. Flag naming guessable?        Contradiction F1     BLOCKER #2      CONFIRMED → 32
  3. Error messages actionable?    NO — silent = off    #4,#5 breaker   CONFIRMED → 34
                                   (F3)                 trap
  4. Docs findable & complete?     NO (F5,F6)           #6,#7           CONFIRMED → 35,36,37
  5. Upgrade path safe?            YES w/ restart note  YES w/ #8       CONFIRMED → 37
  6. Dev env friction-free?        Eval cmds unpinned   #7,#8           CONFIRMED → 37
```
Claude: 7 findings · Codex: 8 findings · zero disagreements.

## AMENDMENTS (auto-decided, folded)
| # | Amendment | Source |
|---|---|---|
| 32 | ONE provider knob: `LABELCHECK_VLM_PROVIDER` (fixture is a value; read_crop → None under it, documented). D-5 text corrected | DX-F1, C#2 |
| 33 | Fixture keyed by (sample, field) — never crop bytes; a NAMED troubled training sample ("Bad photo") must yield ≥1 chip; e2e test asserts it; exact one-line command in D-6 AND README | DX-F2, C#1 |
| 34 | Startup config line ("mm second read: enabled provider=X key=present|ABSENT — inactive"); "Verify it's on / it's broken" doc section; breaker-open recorded once in debug block with state + retry time + mode key | DX-F3, C#4,#5 |
| 35 | Full MM_READ × provider × key matrix table in D-6 (what-you-see per cell); MM_READ=1 + provider=off ⇒ off wins; "MM = multimodal second read" glossed at first use | DX-F4, C#3 |
| 36 | Provider-neutral doc `docs/enable-second-read.md` (stub pointer left in enable-azure-vlm.md); `.env.example` gains commented MM/VLM vars; README one-liner under samples | DX-F5, C#6,#7 |
| 37 | Runnable commands pinned: fast tier rides `make test`; live tier exact pytest one-liner with skip reasons naming every required var; env-only rollback one-liner; flags read at process start — compose needs `--force-recreate` | DX-F6,F7, C#7,#8 |

## DX scorecard (initial → after amendments)
```
Getting started    2/10 → 9/10   TTHW: unbounded → <5 min (pinned command)
Flag ergonomics    5/10 → 8/10   Error experience  3/10 → 8/10
Docs               4/10 → 8/10   Escape hatches    6/10 → 9/10
Naming             6/10 → 8/10   Upgrade/rollback  8/10 → 9/10
Eval ergonomics    5/10 → 8/10   OVERALL           4.9 → 8.4
```

## Developer journey (evaluator persona, after amendments)
```
1 clone → 2 make dev (existing) → 3 README line points at demo →
4 LABELCHECK_MM_READ=1 LABELCHECK_VLM_PROVIDER=fixture compose up →
5 open Sample "Bad photo" → 6 chip on troubled row ≤15 s → 7 debug
block shows provider=fixture → 8 (optional) live tier w/ real key →
9 rollback: unset flag, --force-recreate
```
Empathy note: before amendments the evaluator's step 4 produced a
byte-identical app with no signal — the feature read as vapor; the
named-sample + startup-line + labeled-chip triad makes every state
(working / off / misconfigured / breaker-open) visibly distinct.

---

## Cross-phase themes
- **Silent states must be visibly distinct** — flagged independently by CEO
  voices (demo invisibility) and both DX voices (misconfig = off). High-
  confidence signal; resolved: fixture demo, startup line, labeled chip states.
- **"Reuse" claims vs code reality** — CEO (mistral "dialect"), Eng (judge
  "same compare", provider default), DX (flag-name drift): every phase caught
  an assertion the code contradicted. Resolved by amendments 3, 16–21, 32.
- **Measure before build** — both CEO voices demanded evidence (→ D-0); both
  eng voices refined WHICH population to measure (eligible set + cap).

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | clean (via /autoplan) | 4 proposals, 0 accepted, 4 deferred; 32 voice findings → 15 decisions |
| Codex Review | `/codex review` | Independent 2nd opinion | 3 | issues_found (via /autoplan) | CEO 20 + Eng 18 + DX 8 findings, all absorbed |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean (via /autoplan) | 30 issues → 16 amendments, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | no UI scope beyond Section 11 chip states |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | clean (via /autoplan) | score 4.9→8.4, TTHW unbounded→<5min, 6 amendments |

- **CROSS-MODEL:** three phases of dual voices; zero unresolved disagreements —
  every cross-model confirmation became a plan amendment (37 total).
- **VERDICT:** CEO + ENG + DX CLEARED — ready to implement pending final gate
  approval; D-0 is the first task and remains a stop-gate.

NO UNRESOLVED DECISIONS
