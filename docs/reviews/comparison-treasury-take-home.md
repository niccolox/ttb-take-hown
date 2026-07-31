# Comparison: our PLAN.md vs zukeoh/treasury-take-home

Cloned to `comparisons/treasury-take-home` (2026-07-31). ~4,950 lines of Python (FastAPI, server-rendered Jinja2) + 662 lines of JS, 64 tests, 50 synthetic sample labels, deployed on Render. Of the three competitors surveyed, this is the closest architectural sibling to our plan — and the strongest on the statutory warning.

## Where we converged

| Decision | Them | Our plan |
|---|---|---|
| OCR | Local EasyOCR/Tesseract behind a provider Protocol, CPU, no cloud | Local PaddleOCR behind an `Extractor` interface |
| Extraction | **Expected-value-guided**: sliding window of OCR fragments scored by `WRatio × token-coverage` | Targeted verification — same core insight |
| Fuzzy matching | rapidfuzz, per-field thresholds (brand 82/62, class 78/58) | rapidfuzz, per-field length-calibrated thresholds + ambiguity margin |
| Warning caps | Case-sensitive `GOVERNMENT\s+WARNING\s*:` regex + case/punctuation-preserving substring match; title-case test exists (`test_warning_validator.py:61`) | Case-sensitive prefix sub-check on raw OCR + exact text compare |
| Bold | Informational "typography & physical size" row, always NEEDS REVIEW, never affects overall | Stroke-width heuristic with M0 kill-gate → "confirm visually" fallback |
| Low confidence | `avg_conf < 0.55` converts FAIL → NEEDS REVIEW; zero fragments → all NEEDS REVIEW | `readable` gates + coverage model → NEEDS REVIEW |
| Verdicts | PASS / FAIL / NEEDS_REVIEW; overall = worst consequential | 5 states + two-axis overall |
| Batch intake | CSV (BOM-tolerant, validated, template download) or per-file manual forms | CSV manifest or per-file inline |
| DX | Docker with baked EasyOCR weights, healthcheck, pinned CPU torch | Docker with baked models, /healthz after warmup |

**Correction to our earlier three-way claim:** ttb-label-reviewer and aicola both miss the title-case trap; this candidate catches it, from real OCR output, with a test. On the flagship check they are our peer.

## Where they beat the plan (adopt)

1. **Reviewer override workflow** (`results.js:100-135`): per-card PASS/NEEDS REVIEW/FAIL override buttons, an "Overwritten: X → Y" note, and the export carrying `original_result / final_result / overwritten` columns. That's Dave's judgment made first-class — the tool screens, the agent decides, and the record shows both. We have the framing but not the mechanism. **Adopt.**
2. **Per-field regulatory citations**: every `FieldResult` carries `requirement_basis` + TTB source name/URL (`references.py`) rendered in a "Requirement & Source" column — a lightweight version of COLAClear's cited checks and a strong "attention to requirements" signal. **Adopt.**
3. **Programmatic adversarial label generator** (`generate_test_data.py`, 40 named variant categories: rotation angles, mirror, perspective, curved-can shading, glare, torn/taped/water-stained, cropped warning, case variation…). Controlled ground truth beats AI-generated images for regression fixtures; their fixture-quality benchmark asserts per-image field-recovery floors. **Adopt the generator approach for our golden set.**
4. **Warning-required trigger rule**: warning demanded when *detected* ABV ≥ 0.5% (OCR overrides application data), with a non-alcoholic escape — a rule detail our plan lacks.
5. **Memory telemetry as a first-class module** (RSS + stage traces) born from a real Render OOM crash — empirical support for our "measure per-worker memory at M0" line.
6. Honest test-data caveat: all 50 fixtures come from one synthetic generator — "useful for regression, not for claiming real-world accuracy." Same posture as our corpus split.

## Where our plan beats them

1. **Latency is unaddressed.** No measured numbers anywhere; the UI estimates 3.5s/image, and the README warns Render batches "may take several minutes." The 5-second stakeholder requirement — the brief's loudest signal — is never engaged as a target. Our M0 gate on target hardware exists precisely for this.
2. **The deploy tier forced an accuracy downgrade.** EasyOCR (better) was swapped for Tesseract on Render to fit starter-tier memory, trading away accuracy on "severe angles, blur, decoration, curvature" — Jenny's requirement sacrificed to a $7 hosting decision. Our plan sizes the instance from M0 measurement and says the cost out loud.
3. **Evidence is computed and then thrown away.** Both providers populate `OcrBlock.bbox`, and no crop or box ever reaches the UI — results show a full-image thumbnail and a text table. Our coordinates-based evidence crops are the trust feature both our outside voices ranked highest; they left it on the floor.
4. **One synchronous POST for a whole 300-image batch** — acknowledged HTTP-timeout risk, no per-item retry, no cancel, no streaming rows; concurrency 1 on the deployed tier. Our job API (submit/status/result/cancel, priority for single verifies) is the answer to exactly this.
5. **Net contents is metric-only** — "25.4 fl oz" (in the brief's own domain) doesn't parse. Our parser spec includes fl oz conversion.
6. **Rotation coverage**: single 180° retry only (90°/270° label photos fail into low-confidence paths); our plan uses EXIF transpose + the OCR angle classifier.
7. No LIKELY MATCH state (case/punctuation differences fold into fuzzy pass), accessibility self-declared incomplete, results vanish on reload with only a JS confirm guard.

## Four-way standings

| | aicola (cloud LLM) | ttb-label-reviewer (41k LOC) | treasury-take-home | our PLAN.md |
|---|---|---|---|---|
| 5s requirement | 5-15s, admitted miss | 4.15s median on RTX 4090 | Unmeasured; "minutes" on deploy | M0 gate on target CPU + fallback ladder |
| Title-case warning trap | Rests on LLM fidelity | **Missed** (`.upper()` both sides) | **Caught** (case-sensitive + tested) | Caught (case-sensitive sub-check) |
| Evidence provenance | None | Crops (+ estimated fallbacks) | bboxes computed, never shown | Coordinate crops, honest fallback |
| Batch robustness | Parallel browser calls, tens only | Client slots + real queue/scheduler | One sync POST, timeout risk | Job API, per-item retry/cancel |
| Reviewer workflow | None | Per-field pass/fail + notes | **Override + audit columns in export** | Planned (adopt theirs) |
| Tests/fixtures | 0 | ~240 + goldens + real COLA corpus | 64 + 50-label generator + quality floors | Planned: units + goldens + eval gates |

## Verdict

The most requirements-literate competitor: right architecture, right warning rigor, right honesty. Its two structural losses are the ones our review pipeline spent the most ink on — latency was never measured (and the deployed configuration quietly gives up on both speed and accuracy), and the evidence layer that builds agent trust was computed but never shown. Adopt their reviewer-override export, per-field citations, warning-trigger rule, and programmatic fixture generator; keep our job API, evidence crops, latency gates, and fl-oz parsing.
