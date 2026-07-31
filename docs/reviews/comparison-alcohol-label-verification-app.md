# Comparison: our PLAN.md vs ambika-garg/alcohol-label-verification-app

Cloned to `comparisons/alcohol-label-verification-app` (2026-07-31). Seventh entrant, and a close genetic relative: its git history is built directly on the same assignment repo as ours (shared commit `62bd63c`). All-TypeScript: **Gemini 2.5 Flash extraction + deterministic TS verification**, deployed as Vercel serverless functions (plus a parallel Express/React/Docker variant of the same code), 40 backend tests, heavy AI-assistant scaffolding left in-repo (`claude.md`, `GEMINI.md`, `AGENTS.md`).

## The remarkable part: their warning design is our warning design

`GovernmentWarningValidator` runs **three independent sub-checks** — presence (case-sensitive `GOVERNMENT WARNING:`), format (isBold attribute), text accuracy — returning per-sub-check results plus an overall. That's structurally the same shape as our plan's text / prefix-caps / bold triple (independently derived, or convergent AI-era design). The differences are where the defects live.

## Three defects, in ascending order of severity

1. **Text accuracy is ≥95% LCS, not exact.** Word-level longest-common-subsequence on lowercased words, threshold 0.95: one substituted word in the 45-word statutory text scores 97.8% and **passes** ("birth defect" vs "birth defects" survives). LCS is also insertion-blind — extra words inserted into the warning don't lower the score (it divides by canonical length only). Better than parth33320's order-blind `token_set_ratio`, still not Jenny's word-for-word.

2. **The caps check rides on Gemini transcription** — `text.includes('GOVERNMENT WARNING:')` runs on LLM-extracted text (the prompt asks for the warning "word for word"), the same fidelity dependence as aicola, GPT-4o, and petabase. Fourth LLM-extraction build with this structural weakness.

3. **The all-green verdict is unreachable — a dead check.** `WarningFormatAttributes` exists only in `types.ts`; nothing ever constructs it — the extraction prompt has no format fields, and the service calls `validate(extractedValue)` with one argument (`labelVerificationService.ts:250`). So `checkFormat(null)` always returns `passed: false` ("Format attributes not available"), `overallPass = subResults.every(passed)` is **always false**, warning confidence is pinned to 0, and `isOverallMatch()` — which requires the warning to match — **can never return true for any label, including a perfect one**. The unit tests (17 on the validator) pass attributes directly and never catch the integration gap. The commit titled "Government Warning Strict Validator with 3 sub-checks" shipped a validator that structurally fails everything; the commit titled "three-tier matching + agent override" shipped no override code at all (repo-wide grep: zero hits).

Defect 3 is the sharpest lesson of the whole competitor survey: **a per-unit-tested component wired unreachably is worse than no check, and only an end-to-end reachability test catches it.**

## Rest of the picture

- Three-tier matching (exact → normalized/Levenshtein ≥0.85 → mismatch) with a single global threshold — no per-field calibration, no ambiguity margin.
- `isOverallMatch` counts only brand, ABV, warning as critical — **a net-contents mismatch doesn't block the overall verdict** despite net contents being a core brief field.
- Batch: CSV + zip intake (busboy + adm-zip, same pattern we adopted from petabase) through serverless functions — but Vercel function limits (body size, duration) go unaddressed for 300-label zips, and there's no rate limiting in front of the server-side Gemini key.
- No evidence provenance, no confidence gates (extraction is trusted or NOT_FOUND), no absent-vs-unreadable distinction (NOT_FOUND → mismatch), no measured latency anywhere.
- Duplicated codebase (lib/ for Vercel, backend/src for Express) — two copies of the verification logic to keep in sync, the exact drift risk our single-source normalization module rule targets.

## What we take from this one

- **Adopt: a full-path reachability test** — `make smoke` must assert that the clean golden sample produces the all-green verdict *through the deployed API path*, not just that components pass unit tests. This is the test that would have caught their dead check, and it becomes our guard against the same class of wiring bug.
- Their CSV+zip serverless intake confirms the petabase adoption; nothing else new.

## Verdict

The closest anyone came to our warning architecture — and the strongest demonstration in the survey that design without integration verification is worthless: the flagship validator can never pass, the advertised override doesn't exist, and 40 green unit tests hid both. Against our plan it loses on the same axes as the other LLM-extraction builds (transcription-fidelity caps check, no provenance, no absent semantics) plus the dead-check wiring. The survey's meta-lesson lands here hardest: **every check must be provably reachable end-to-end** — now a TODO'd smoke-test requirement in our plan.
