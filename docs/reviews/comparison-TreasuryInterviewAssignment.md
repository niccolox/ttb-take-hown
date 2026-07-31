# Comparison: our PLAN.md vs peter-strizhev/TreasuryInterviewAssignment

Cloned to `comparisons/TreasuryInterviewAssignment` (2026-07-31). Fifth architecture flavor: **GPT-4o vision extraction (OpenAI Chat Completions, JSON mode) + graduated deterministic matching**, FastAPI service layer + Next.js/Tailwind client, Render + Vercel deploys, in-memory async batch queue. ~1,200 lines of API Python, 9 test files, 15 adversarial test images with a manifest, and a genuinely candid `PostMortem.md`.

## Their shape

- `AnalysisService` orchestrates two timed stages (OCR → validation) and returns per-stage metrics; the UI displays elapsed time and a preprocessing audit trail (each Pillow step — resize, autocontrast, contrast boost, sharpen — is returned as a structured entry).
- Matching ladder per field (`validation.py`): missing → exact → case/whitespace-normalized → punctuation-stripped → `difflib.SequenceMatcher` similarity vs threshold. Non-exact equivalences become `WARNING` (review), never auto-pass — deliberately "biased toward warnings and failures."
- **Warning is a specialized path, correctly ordered**: presence → `startswith("GOVERNMENT WARNING:")` case-sensitive caps check → whitespace-normalized exact wording; response carries explicit `present/caps/exact` booleans. Test image `label_02_warning_titlecase_fail.png` targets the trap directly.
- Anti-hallucination guard: each structured field must appear in the raw OCR text or it's dropped — defends against invented fields.
- Batch: in-process `asyncio.Queue` + background worker, sequential via `to_thread`; state is process-local (restart clears it). Post-mortem admits the CSV expected-values mapping for batches ran out of time.
- Test images include a novel adversarial category the other four lack: **photos of screens** (moiré, low-contrast screen shots, upside-down screen photos) alongside rotation, perspective glare, shadow occlusion, motion blur, partial crops.

## Where they're strong (adopt)

1. **Preprocessing audit trail surfaced to the user** — the UI shows exactly how the image was transformed before OCR. Cheap transparency that builds exactly the trust our evidence-crops aim at, from a different angle. **Adopt**: our staged pipeline should report which preprocessing (raw vs corrective pass) produced the result, per image.
2. **Stage timing metrics rendered in the results UI** — our response envelope already carries `timing_ms`; surface it in the detail panel like they do.
3. **Photos-of-screens / moiré golden-set category** — agents will absolutely photograph a monitor showing label artwork; none of our 40 planned variant categories covers it. **Adopt into the generator.**
4. **Caps-before-wording check ordering with explicit `present/caps/exact` sub-flags** — mirrors our three-sub-result design; their response shape confirms the pattern independently.
5. The post-mortem itself: honest stage-by-stage delivery narrative, assumptions, and future work — a good writing model for our README's trade-offs section.

## Where our plan wins

1. **The caps check rests on GPT-4o transcription fidelity** — same structural weakness as aicola: `startswith("GOVERNMENT WARNING:")` runs on model-transcribed text, and vision LLMs autocorrect memorized statutory text toward its canonical all-caps form. Their anti-hallucination guard doesn't help (it validates against raw OCR text *from the same model*). They aimed at the right trap — the test image exists — but the architecture can't guarantee the evidence reaching the check. OCR-verbatim input is the only reliable substrate, which is our pivot's core dividend.
2. **"Missing field" is a hard compliance failure.** `found is None` → `NON_COMPLIANT` ("Field not detected on label"), even though the stated fix is "retake the photo" — a system/photo limitation rendered as a compliance verdict. No unreadable-vs-absent distinction, no coverage model; our reason-coded NEEDS REVIEW taxonomy and text-mass gate exist precisely for this. (Same defect class as petabase's JSON-parse-FAIL.)
3. **No numeric parsing anywhere**: ABV and net contents are compared as strings through the same ladder — "45% Alc./Vol. (90 Proof)" vs an application "45%" lands in similarity territory, and "750 mL" vs "0.75 L" is a mismatch. Our parser grammar (percent/proof equivalence, unit conversion incl. fl oz) covers the brief's own sample data; theirs doesn't.
4. **Dave's requirement is inverted**: every case/punctuation-equivalent match demands review (`WARNING`), so "STONE'S THROW" vs "Stone's Throw" — the brief's canonical should-pass case — always flags. Cautious, but it converts the highest-volume trivial equivalence into per-label review work; our LIKELY MATCH chip surfaces it as "confirm" without blocking the all-clear banner.
5. **No evidence provenance** (GPT-4o returns no coordinates; raw OCR text + preprocessing audit is the whole trail), **ephemeral batch state** (server restart loses jobs mid-run), no batch CSV mapping (admitted), no rate limiting on a public API fronting a paid OpenAI key, and latency "satisfies the performance target" per the post-mortem but no measured numbers are published anywhere.
6. **A branding caution, not a code issue**: the client reuses visual assets and styling from official U.S. Treasury web properties (with a disclaimer footer). For a federal hiring exercise that's a risky call — official insignia use is legally restricted, and a disclaimer doesn't cure the look. Our plan's "quiet product identity" line deliberately avoids this.

## Six-way standings

| | aicola (Claude) | ttb-label-reviewer (local, 41k) | treasury-take-home (Tesseract) | TakeHomeProject (Gemini) | TreasuryInterviewAssignment (GPT-4o) | our PLAN.md |
|---|---|---|---|---|---|---|
| Title-case trap | LLM-fidelity-dependent | missed | **caught + tested** | auto-passes on crisp photos | right check, LLM-fidelity-dependent (test image exists) | caught on verbatim OCR |
| Absent/unreadable semantics | prompt-delegated | coverage-blind MISMATCH risk | conf<0.55 → review | parse-fail → FAIL | missing → NON_COMPLIANT | reason codes + coverage gate |
| Numeric parsing | prompt-delegated | ±0.25/±1mL tables | metric-only | none | **none (pure string)** | full grammar incl. fl oz |
| Evidence | none | crops (+estimated) | computed, unused | none | preprocessing audit only | coordinate crops + audit (adopted) |
| Batch | browser fan-out, tens | client slots + real queue | one sync POST | 21 min/300 | in-memory queue, ephemeral, no CSV map | job API + manifest |
| Measured latency | 5-15s admitted | 4.15s on 4090 | none | ~4.2s/call serialized | claimed met, unmeasured | M0 gate + published artifacts |

## Verdict

The most *architecturally literate* cloud entrant — service layers, typed contracts, correct warning-check ordering, transparency features, and an honest post-mortem — sitting on the same foundation crack as every LLM-extraction build: the caps check can only be as faithful as the model's transcription, and the fallback semantics (missing → non-compliant) punish the photo instead of routing to a human. Adopt their preprocessing audit trail, in-UI stage timings, and the photos-of-screens test category; keep our verbatim-OCR substrate, coverage-gated absence semantics, numeric parsing, and durable batch path.
