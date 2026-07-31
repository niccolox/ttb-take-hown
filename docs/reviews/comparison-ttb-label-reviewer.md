# Comparison: our PLAN.md vs Esemianczuk/ttb-label-reviewer

Cloned to `comparisons/ttb-label-reviewer` (2026-07-31). Their repo: ~41k lines of source (109 py / 99 tsx / 41 js files), 18 docs, 75-record COLA fixture corpus, hosted demo. Built in ~2 days of commits (2026-06-15/16).

## Where we converged independently (strong signal the architecture is right)

| Decision | Them | Our plan |
|---|---|---|
| OCR engine | PaddleOCR 3.2, fully local, zero cloud/LLM calls | PaddleOCR PP-OCRv4, fully local (user premise-gate decision) |
| Decision authority | 100% deterministic rules (~1,350-line validator) — no model decides pass/fail | Deterministic rules engine — "the LLM/OCR never decides compliance" |
| Verification style | Sliding token-window search of expected values over OCR tokens | Targeted verification ("search for expected values, don't classify blind") |
| Fallback engine | tesseract.js browser demo with vendored wasm | tesseract.js documented as the zero-infra alternative at M0 |
| Verdict taxonomy | PASS/FAIL/WARNING/NEEDS_REVIEW/NOT_FOUND/NOT_APPLICABLE | MATCH/LIKELY_MATCH/MISMATCH/NEEDS_REVIEW/NOT_CHECKED |
| Evidence | Per-field crop thumbnails from OCR bboxes + zoom/pan workbench | Evidence crops from bboxes, click-to-enlarge, region-on-full-image |
| Batch concurrency | Client-side slots, default 2, cap 4 | Client-orchestrated via job API, concurrency ~4 |
| Design language | USWDS-inspired palette/typography, axe-core scans | Public Sans (USWDS), WCAG 2.2 AA as M1 criteria |
| Cross-engine goldens | 16 shared JSON golden cases run by both Python and JS suites | Golden set + snapshot-pinned eval harness (M0) |

Their `docs/ML_APPROACH_EVALUATION.md` also did our M0 empirically: benchmarked EasyOCR, docTR, TrOCR, CLIP ranking, and **built then rejected a LayoutLMv3 field extractor** on a stated promotion gate (field recall 0.398, false-pass 0.818). Measurement-gated architecture — same philosophy as our M0 spike.

## Where they beat the plan (things worth stealing)

1. **Vertical/rotated warning recovery** (`paddleocr_engine.py:503-585`): crops candidate regions, re-OCRs at 90/180/270, keeps the best-scoring variant, maps boxes back. More surgical than our global-deskew idea; slot into our conditional-preprocessing stage.
2. **Real fixture corpus**: 75 public COLA records / 126 label images scraped by a purpose-built collector. Real labels > AI-generated labels for calibration; our ~25-image set should include public COLA images if timebox allows.
3. **Measured, published benchmarks with artifacts** (`docs/BENCHMARKS.md` + JSON results): median 4.15s, p95 4.43s single review; concurrent batch 1.5x speedup, 0 mismatches vs sequential. Exactly the "measure, don't assert" posture our plan demands — they shipped it.
4. **ABV↔proof tolerance ±0.25 and net-contents ±1 mL** — practical tolerances vs our strict stated-precision equality; worth adopting with documentation.
5. **COLA JSON/XML import in the applicant wizard** — their version of our deferred "application-side ingestion" TODO; proves it's buildable in scope.

## Where our plan beats them (the gaps that matter for grading)

1. **They miss the planted trap.** Their warning check calls `.upper()` on both sides before comparing (`label_validators.py:1290-1293`) and has **no capitalization check anywhere** — a title-case "Government Warning:" passes identically. Jenny's interview explicitly names this as a rejection she caught. Their warning match is also fuzzy (segments ≥0.9 → PASS, all six ≥0.75 → "PASS with OCR noise"), not exact-match. Our plan makes the case-sensitive all-caps prefix its own sub-check and keeps text comparison exact with a three-outcome honesty model. **This is the single highest-leverage differentiator.**
2. **The 5s number needed an RTX 4090.** Their hosted worker hits 4.15s median *on GPU*; their CPU path is undocumented for latency. This validates our eng-phase alarm: PaddleOCR full-image on shared vCPUs will not casually meet 5s. Our M0-on-target-hardware gate plus mobile-model option is the honest CPU answer; their data says treat it as the top risk.
3. **Scope discipline.** The brief says "a working core application with clean code is preferred over ambitious but incomplete features." They shipped RBAC, signed tokens, audit log, a 580-line hardware-aware scheduler, admin retention ops, WebSockets, mDNS, and a second full app — and their Known_LIMITATIONS admits backend parity gaps and fixture-based benchmark shortcuts. Our plan spends that budget on the graded criteria: exactness of the core checks, error handling, evaluator experience.
4. **Estimated evidence crops.** When OCR finds no box they fall back to hard-coded ratio regions (`evidenceCrops.ts:56-68`, `source: "estimated"`) — showing a crop of where a field *usually* is. Our plan's rule (no box → verbatim text fallback, never fake provenance) is more honest evidence design.
5. **Preprocessing**: theirs is 13 lines (size only) with orientation classifiers disabled; bad-photo robustness rests on one rotation-recovery path. Our plan's conditional preprocessing + EXIF handling + coverage gate is a more complete answer to Jenny's imperfect-photo requirement.
6. **Latency escalation is dead code**: their `targetLatencyMs: 5000` is recorded but never acted on (`validation_task.py:269-278`). Our >10s → NEEDS_REVIEW(system) + retry path is live behavior.

## Verdict

Same architectural species (local OCR + deterministic rules + evidence crops), radically different budgets. They spent ~41k lines going *wide* (roles, scheduler, admin, second app) and left the brief's sharpest trap uncovered (all-caps warning) while needing a 4090 to make latency. Our plan goes *deep* on the graded axes: exact+caps+bold warning model, honest uncertainty states, measured-on-target latency, and evaluator-first DX. Adopt their rotation recovery, tolerance values, real-COLA fixtures, and benchmark-artifact publishing; keep our warning rigor, scope restraint, and provenance honesty.
