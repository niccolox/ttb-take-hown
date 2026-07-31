# Comparison: our PLAN.md vs parth33320/OCR-Alcohol-Label-Validator

Cloned to `comparisons/OCR-Alcohol-Label-Validator` (2026-07-31). The minimalist entrant: **local Tesseract (pytesseract) + rapidfuzz in a single ~250-line FastAPI file**, Next.js/Tailwind single page, docker-compose, an e2e script that asserts the <5s requirement. 460KB total. Firewall-native by choice, same as our pivot ("100% offline capability… no cloud ML dependencies").

## Their shape

- Preprocess (grayscale → 1600px cap → 2× contrast) → Tesseract `--oem 1 --psm 11` in a 2-worker thread pool, model warmed at startup (the same warmup trick our plan mandates).
- Three checks only: brand (fuzzy vs best line and full text), ABV (regex + `isclose` ±0.1), government warning. **No net contents, class/type, or any other field** — two of the brief's core fields absent.
- Statuses PASS/WARNING/FAIL; overall = worst. `e2e_test.py` asserts correctness and the <5s budget.
- Git history shows three agent-generated "optimization" PRs merged then reverted; `CLAUDE.md`/`AGENTS.md` scaffolding left in the frontend.

## The warning check, dissected

**They catch the caps trap** — the second local-OCR build to do so: `re.search(r"GOVERNMENT\s+WARNING\s*:", full_text)` runs **case-sensitive on raw Tesseract output** (`main.py:114`), so title-case → FAIL "Missing colon or not in all caps." Verbatim substrate, correct check.

**But the wording check has a structural defect**: it scores `fuzz.token_set_ratio(expected_norm, full_norm)` where `full_norm` is the *entire label text*, uppercased (`main.py:117`). `token_set_ratio` is order-insensitive and set-based — when the expected tokens are a subset of the label's tokens, it scores ~100 **regardless of word order or position**. Consequences:

- A warning with its words **scrambled or reordered** passes at ~100 ("word-for-word" requirement violated).
- Warning words scattered across the label (some in the warning block, some in marketing copy) can still assemble a passing score.
- At the ≥95 PASS band, a single substituted word in the 40-word statutory text may survive; the 85-94 band ("wording might have minor discrepancies") turns Jenny's zero-fuzziness field into a judgment call.

Our plan's anchor → block reconstruction → whitespace-only-normalized **exact** compare with word-level diff exists precisely because fuzzy scoring is the wrong tool for statutory text.

## Other gaps vs our plan

1. **Batch applies ONE application to every file** — `/batch` takes a single `brand_name/abv/government_warning` for all images (`main.py:238-247`). The 200-300 importer scenario is 300 *different* applications; there is no per-file data path, no CSV, no manifest. The batch feature demos batch and cannot do the job the brief describes.
2. **No absent/unreadable semantics**: a blurry or non-label image FAILs every field (false red); there's no NEEDS REVIEW routing, no confidence gate on OCR quality (Tesseract confidences are available and unused), no coverage concept.
3. **No proof↔ABV conversion**: a proof-only label ("90 Proof") vs an ABV application value ("45%") FAILs — `isclose(45, 90)` — despite the brief's own sample pairing them.
4. **No evidence provenance** (extracted-text dump only), no image validation (no size caps, no decode guards, `Image.open` on raw bytes), CORS `*`, no rate limiting on public deploy, no tests beyond the e2e script and a smoke `test_api.py`.
5. **Two core fields unimplemented** (net contents, class/type) — a completeness gap none of the other five competitors has.

## What they got right (and one adoption)

- The right substrate (local OCR, verbatim case), the right deployment posture (docker-compose up), the warmup-at-startup trick, thread-pool offloading, and sensible Tesseract tuning — the same first four moves our eng phase specified.
- **Adopt: an explicit <5s assertion in the CI smoke test.** Our plan publishes measured p50/p95; their `e2e_test.py` goes one step further and *fails the build* when the budget is missed. Cheap and honest — add the assertion to `make smoke`.

## Seven-way standings (compressed)

| | Caps trap | Exact wording | Per-file batch data | Absent≠FAIL semantics | Evidence | Local/5s story |
|---|---|---|---|---|---|---|
| aicola (Claude) | LLM-dependent | regex, case-insensitive | ✅ per-label forms | ✗ | ✗ | ✗ 5-15s |
| ttb-label-reviewer | ✗ missed | fuzzy ≥0.9 | ✅ | partial | ✅ crops | GPU-only 4.15s |
| treasury-take-home | ✅ tested | ✅ substring exact | ✅ CSV | ✅ conf gate | computed, unused | unmeasured |
| TakeHomeProject (Gemini) | auto-pass defect | normalized-equal leaks | ✅ CSV | partial | ✗ | 21min/300 |
| TreasuryInterviewAssignment | LLM-dependent | ✅ exact | ✗ ran out of time | ✗ missing=FAIL | audit trail | claimed, unmeasured |
| **OCR-Alcohol-Label-Validator** | **✅ verbatim** | **✗ token-set defect** | **✗ one form for all** | ✗ | ✗ | ✅ 2-5s asserted |
| **our PLAN.md** | ✅ verbatim | ✅ exact + diff | ✅ manifest + job API | ✅ reason codes + coverage | ✅ crops | M0-gated + asserted (adopted) |

## Verdict

The strongest *instincts-per-line-of-code* of the six — local OCR, warmup, docker-compose, a speed assertion — undone by scope (two core fields missing, batch can't carry per-file data) and by reaching for `token_set_ratio` on the one field where set-based fuzzy matching is disqualifying. It reads like a strong first day of our own M1 that shipped as the final product. Adopt their CI speed assertion; everything else they have, our plan already specifies in a hardened form.
