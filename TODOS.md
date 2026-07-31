# TODOS

Deferred scope from the 2026-07-31 plan review (/autoplan). Format: what / why / effort (human → CC) / priority.

- [ ] **Full 27 CFR rules engine with citations** — Parse Parts 4, 5, 16 into machine-checkable rules; return pass/review/fail with per-rule citations (the commercial COLAClear benchmark is 34 checks/label). Why: turns "does the label match the form" into "is the label legal" — the 10x trajectory. The rules engine is a pure function over extracted fields, so new rules are additive. Effort: XL → L. Priority: P3. Depends on: prototype core shipping.
- [ ] **Multi-image (front/back) label sets** — Accept 1-n images per application and merge extractions; on real bottles the government warning lives on the back label. Why: single-image flow yields "warning missing" on realistic front-label photos. Effort: M → S. Priority: P2. Depends on: extraction schema (extend, don't rewrite).
- [ ] **Retry-with-escalation extraction** — On `readable: partial`, retry with higher effort / image crops before settling on NEEDS REVIEW. Why: fewer human fallbacks; deferred because it adds latency variance against the 5s budget. Effort: M → S. Priority: P3.
- [x] **Visual field highlighting on the label image** — MOVED INTO SCOPE (M2) by the local-OCR pivot: PaddleOCR bounding boxes make evidence crops reliable, so every verdict shows the image region it was read from.
- [ ] **Optional VLM assist for hard photos** — When OCR confidence is low, an *on-prem* vision model (behind the `Extractor` interface) could attempt the read before falling back to NEEDS REVIEW. Why: recovers Jenny's worst-photo cases without violating the no-cloud-API decision. Effort: L → M. Priority: P3. Depends on: M0 fidelity data showing where OCR actually fails.
- [ ] **Beverage-type-aware required-field checklist** — Beer/wine/spirits differ in required fields (e.g., ABV optional for some beer/wine). Status: DEFERRED at /autoplan final gate 2026-07-31. Effort: M → S. Priority: P2.
- [ ] **Application-side ingestion (PDF/screenshot of the COLA form)** — Extract application fields automatically so agents don't re-enter data into a standalone tool; without this, total task time may not beat eyeballing. Why: kills the duplicate-entry tax without requiring COLA integration. Effort: M → S. Priority: P2. (Codex CEO voice, finding 9.)

## From competitor comparison (Esemianczuk/ttb-label-reviewer, 2026-07-31)
- [ ] **Rotated-warning recovery** — Crop candidate warning regions, re-OCR at 90/180/270, keep best-scoring variant, map boxes back (their `paddleocr_engine.py:503`). Slot into our conditional-preprocessing stage. Effort: S → S. Priority: P2.
- [ ] **Practical tolerances** — ABV↔proof ±0.25, net contents ±1 mL (documented), replacing strict stated-precision equality. Effort: S → S. Priority: P2.
- [ ] **Real COLA fixture images** — Pull a subset of public COLA registry label images into the M0 calibration set (they curated 75 records; real labels beat AI-generated for threshold tuning). Effort: S → S. Priority: P2.
- [ ] **Benchmark artifacts** — Publish benchmark JSON results alongside README numbers (their `benchmarks/results/` pattern). Effort: S → S. Priority: P3.

## From competitor comparison (treasurymike/aicola, 2026-07-31)
- [ ] **`foundOn: front|back|both` schema field** — Adopt when multi-image lands; clean way to report which panel carried each field. Effort: S → S. Priority: P3. Depends on: multi-image TODO.
- [ ] **Commodity placement rules** — e.g., wine requires brand/class/ABV on the brand (front) label; fold into the beverage-type checklist TODO. Effort: S → S. Priority: P3.
- [ ] **Foundry-in-Azure cloud-assist variant** — Document Microsoft Foundry (Anthropic models served inside Azure) as a firewall-compliant cloud option behind the `Extractor` interface, alongside the on-prem VLM. Effort: S → S. Priority: P3.
- [ ] **Batch UX: inherit previous label's settings** — New batch rows copy commodity/import flags from the prior row. Effort: S → S. Priority: P3.

## From competitor comparison (zukeoh/treasury-take-home, 2026-07-31)
- [ ] **Reviewer override + audit export** — Per-result PASS/NEEDS REVIEW/FAIL override buttons with "Overwritten: X → Y" note; CSV export carries original_result / final_result / overwritten columns. Why: makes "the agent decides" a mechanism, not a slogan (Dave's judgment). Effort: S → S. Priority: P2.
- [ ] **Per-field regulatory citations** — Each field result carries requirement_basis + TTB source name/URL, rendered as a "Requirement & Source" column. Why: strong attention-to-requirements signal; COLAClear-lite. Effort: S → S. Priority: P2.
- [ ] **Programmatic adversarial label generator** — Script generating golden labels across controlled variant categories (rotations, glare, tears, cropped/taped warning, case variation) with known ground truth + per-image field-recovery floor assertions. Why: controlled ground truth beats AI-generated images for regression. Effort: M → S. Priority: P2. (Replaces/augments the "AI image tools" golden-set approach.)
- [ ] **Warning-required trigger rule** — Require the warning when detected ABV ≥ 0.5% (OCR overrides application data), with a non-alcoholic product escape. Effort: S → S. Priority: P3.

## From competitor comparison (petabase/TakeHomeProject, 2026-07-31)
- [ ] **Mine TTB's official label-examples guide for ground truth** — TTB G 2023-9 (Malt Beverage Label Examples, public PDF) contains the agency's own compliant/non-compliant pairs with stated rejection reasoning; extract images + labels into the M0 calibration corpus. Why: authoritative, free, real ground truth. Effort: S → S. Priority: P2.
- [ ] **Zip upload for batch intake** — Accept a single .zip alongside the CSV manifest; one file beats 300 drag-drops. Effort: S → S. Priority: P2.
- [ ] **Case-insensitive filename matching in the CSV manifest** — Match manifest rows to uploads case-insensitively, echo the uploaded file's original casing. Why: OS/export tools change extension casing invisibly. Effort: S → S. Priority: P3.

## From competitor comparison (peter-strizhev/TreasuryInterviewAssignment, 2026-07-31)
- [ ] **Preprocessing audit trail in the UI** — Report which pipeline path produced each result (raw vs corrective pass, steps applied) as structured entries in the response and a collapsible UI section. Why: transparency that builds agent trust; pairs with evidence crops. Effort: S → S. Priority: P2.
- [ ] **Surface stage timings in the results detail panel** — timing_ms is already in the response envelope; render it (OCR / rules / total) in the detail view. Effort: S → S. Priority: P3.
- [ ] **Photos-of-screens golden-set category** — moiré, screen glare, upside-down monitor photos; agents will photograph screens showing label artwork. Add to the adversarial generator's variant list. Effort: S → S. Priority: P2.

## From competitor comparison (parth33320/OCR-Alcohol-Label-Validator, 2026-07-31)
- [ ] **<5s assertion in CI smoke test** — make smoke should fail the build when the sample-label verify exceeds the latency budget on the target instance, not just report numbers. Why: turns the published p50 into an enforced contract. Effort: S → S. Priority: P2.

## From competitor comparison (ambika-garg/alcohol-label-verification-app, 2026-07-31)
- [ ] **Full-path reachability assertion in make smoke** — The clean golden sample must produce the all-green verdict through the deployed API path (not just unit-level passes). Why: a competitor shipped a per-unit-tested warning validator whose format sub-check was never wired, making PASS structurally unreachable — 40 green unit tests hid it. Effort: S → S. Priority: P1.
