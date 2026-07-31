# Comparison: our PLAN.md vs petabase/TakeHomeProject

Cloned to `comparisons/TakeHomeProject` (2026-07-31). Fourth architecture flavor: **Google Gemini 2.5 Flash Lite (free tier) vision extraction + Python comparison rules**, FastAPI + Jinja2 + HTMX (no frontend framework, no Node), deployed on Hugging Face Spaces. ~900 lines of app Python, no automated tests (admitted). CSV is the *only* input path — no manual form at all.

## Their shape

- One Gemini call per label with a JSON-prompt (not enforced structured output — they regex-strip markdown fences and `json.loads`); model self-rates per-field read confidence 0-100.
- Comparison ladder per field: exact → normalized (case/punctuation-stripped) → substring-partial → mismatch, with a thoughtful confidence blend (match score dominates; read clarity only nudges).
- Verdicts: CONFIRMED / LIKELY / NEEDS_REVIEW / UNREADABLE per field; overall PASS / FAIL / NEEDS REVIEW. LIKELY fields auto-pass at blended confidence ≥ 75.
- Batch: CSV metadata + multi-select images or a `.zip`; all Gemini calls serialized through an asyncio lock at 1 request/4.2s (free-tier 15 RPM); SSE progress bar with running tally; CSV export.
- Test data: a generator that **extracts real labels + ground truth from TTB's own official *Malt Beverage Label Examples* guide (TTB G 2023-9)** — the agency's published compliant/non-compliant pairs with its own rejection reasoning — plus a synthetic generator; 14-image ready-to-run batch with expected results.

## The significant defect: their README contradicts their code on the title-case trap

README assumption #3: "minor case/punctuation drift is **downgraded to a review flag** rather than an automatic pass." The code says otherwise (`verifier.py:181-189, 255-280`): a warning that matches only after case-normalization becomes `LIKELY` with match score 75, blended as `75×0.75 + read_conf×0.25`. For any clearly photographed label (read confidence ≥ 75) that's a blended ≥ 75 — which crosses `AUTO_PASS_CONFIDENCE_THRESHOLD = 75`, so `_overall_status` returns **PASS**. Jenny's title-case rejection *auto-passes precisely when the photo is crisp*. The auto-pass threshold was designed for Dave's brand-name leniency and accidentally swallowed the one field the README says forgives nothing. (Double jeopardy: this assumes Gemini even transcribes case faithfully — the LLM-autocorrect risk means many title-case labels never reach this branch.) This is the exact failure class our plan's per-field asymmetry + case-sensitive prefix sub-check exists to prevent.

Second defect, smaller: a Gemini JSON-parse failure returns `overall_status="FAIL"` (`verifier.py:368-375`) — a *system* error rendered as a *compliance* verdict. Our reason-coded NEEDS REVIEW(`system error`) taxonomy exists for exactly this; an agent seeing FAIL because the model emitted malformed JSON is a false rejection.

## Where they're genuinely strong (adopt)

1. **Real TTB ground truth, free and authoritative**: mining TTB's own published label-examples guide for compliant/non-compliant pairs *with the agency's own stated reasoning* is the best test-data idea across all four competitors. **Adopt for our M0 calibration corpus** (their `extract_real_labels.py` approach; the PDF is public).
2. **CSV-first input model**: "there's no manual form-filling: the CSV is the input, mirroring how this data already exists digitally in a real COLA submission." A sharp product argument that supports our CSV-manifest path and our deferred application-ingestion TODO — though dropping the manual form entirely overshoots (Sarah's mother isn't authoring CSVs; our dual-path keeps both).
3. **Zip upload for large batches** — one file beats 300 drag-drops; cheap to add to our batch intake.
4. **Case-insensitive filename matching** between CSV and images with original-casing echo — a real-world papercut fix for our manifest spec.
5. Honest 429 handling: no silent retries; a plain-language quota message telling the agent exactly what happened and what to do.
6. Single-language stack (no Node build) is a legitimate simplicity play for this brief — our static-export decision gets most of the same benefit while keeping React for the master-detail UI.

## Where our plan wins

1. **The 300-label scenario takes ~21 minutes** (admitted): serialized 4.2s/call on the free tier. Janet's importer-dump requirement is priced at zero dollars instead of met. Our local pipeline does it in ~2 minutes on hardware we size at M0.
2. **Cloud dependency with the weakest firewall story of the cloud entrants**: "one predictable domain to allowlist" is honest but thin next to aicola's Foundry-in-Azure proposal — and both lose to local-by-construction.
3. **Model self-rated confidence is load-bearing** — Gemini's 0-100 self-scores gate auto-pass decisions; our Phase 1 review flagged exactly this (LLM self-confidence is poorly calibrated, which is why our plan uses OCR word confidences + a coverage model instead).
4. **Mismatch = "FAIL … fails compliance unless corrected"** — verdict language that overstates the tool's authority; our screening-assistant framing ("the agent decides") is both the honest posture and the adoption politics.
5. **No evidence provenance** (no crops, no boxes, raw extraction hidden in a collapsible), **no bold check of any kind**, **no automated tests** (generator exists, nothing runs it — our eval harness is a milestone deliverable), and net-contents/ABV comparison is string-normalization only (no unit conversion: "750 mL" vs "0.75 L" mismatches).

## Five-way standings

| | aicola (Claude) | ttb-label-reviewer (41k LOC) | treasury-take-home (Tesseract/EasyOCR) | TakeHomeProject (Gemini) | our PLAN.md |
|---|---|---|---|---|---|
| 5s / batch scale | 5-15s; tens only | 4.15s on RTX 4090 | unmeasured; "minutes" | ~5s single; **21 min/300** | M0-gated; ~2 min/300 |
| Title-case trap | rests on LLM fidelity | missed (`.upper()`) | **caught + tested** | **auto-passes on crisp photos** (code contradicts README) | caught (case-sensitive sub-check) |
| Decision authority | mostly model | rules | rules | rules over LLM extraction | rules over OCR |
| Evidence | none | crops (+estimated) | computed, unused | none | coordinate crops |
| Test data | none | real COLA corpus (75) | 50-label generator | **TTB's own guide + generator** | generator + real COLA (adopted) |
| Automated tests | 0 | ~240 | 64 | 0 | planned, milestone-gated |
| Unit conversion | prompt-delegated | ±0.25/±1mL tables | metric-only | none | full incl. fl oz |

## Verdict

The best *product thinking* of the cloud entrants (CSV-first, SSE progress, real TTB ground truth, honest trade-off writing) undermined by the two things code review exists to catch: an auto-pass threshold that silently neutralizes their own stated warning strictness, and system errors dressed as compliance verdicts. Adopt their TTB-guide data mining, zip intake, and filename-matching papercut fix; keep our asymmetric strictness (enforced in code, tested), reason-coded error taxonomy, evidence crops, and a batch path that meets the 300-label scenario in minutes rather than pricing it at $0 and 21 of them.
