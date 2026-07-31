<!-- /autoplan restore point: /home/niccolox/.gstack/projects/niccolox-treasury-instructions/main-autoplan-restore-20260731-110733.md -->
# PLAN: AI-Powered Alcohol Label Verification App (TTB Take-Home)

> **Architecture decision (user, premise gate 2026-07-31):** local/OCR, firewall-native.
> No cloud ML API anywhere in the pipeline. This reversed the original vision-LLM
> approach; both outside voices' key objections (verbatim fidelity, visual provenance,
> procurement relevance) are resolved by construction under this architecture.

## Problem

TTB compliance agents review ~150k label applications/year by eye. Most of the work
is field matching: does the label artwork say what the application form says? The
prototype verifies a label image against application data and returns per-field
results fast enough that agents actually use it.

Hard requirements from stakeholder interviews (README.md):

1. **Speed**: results in ~5 seconds per label or agents abandon the tool (Sarah, prior vendor failed at 30-40s).
2. **Simplicity**: UI usable by a 73-year-old with minimal tech comfort. Large targets, obvious flow, no hunting.
3. **Batch uploads**: importers dump 200-300 applications at once; process many labels in one go.
4. **Government warning is exact-match**: word-for-word statutory text, "GOVERNMENT WARNING:" must be ALL CAPS (Jenny caught a title-case rejection). No fuzziness here.
5. **Brand name needs judgment**: "STONE'S THROW" vs "Stone's Throw" is a match (Dave). Case/punctuation differences should not hard-fail.
6. **Imperfect photos**: angles, glare, bad lighting — degrade gracefully to "needs human review", never a false PASS.
7. **Standalone prototype**: no COLA integration, no PII, deployed URL + repo with README.
8. **Firewall-native (user decision)**: TTB's network blocks outbound ML endpoints — the prior vendor's features died on this (Marcus). The pipeline runs entirely on infrastructure we control: no external ML API calls.

## Approach

A single web app around a **local OCR pipeline + deterministic rules engine**:

- **Preprocessing** (OpenCV): deskew, adaptive contrast/threshold, glare mitigation. Bad photos get the same pipeline; what preprocessing can't rescue falls through to NEEDS REVIEW via confidence thresholds — never a false PASS.
- **OCR**: PaddleOCR (PP-OCRv4) server-side — chosen for scene-text strength (angled, curved, stylized label typography). Returns word-level text + bounding boxes + calibrated per-word confidences. OCR is **verbatim by construction**: it preserves case and misspellings, so the planted title-case warning trap is caught naturally, with no LLM autocorrect risk. In-browser tesseract.js is the documented zero-infra alternative; the M0 spike measures both against the golden set before the choice is locked.
- **Targeted verification, not open extraction** (key design insight): the agent supplies the expected values, so the system *searches* for them instead of classifying fields blind:
  - Brand name / class-type: fuzzy-search the application's string across OCR tokens (normalized: case-fold, collapse whitespace, unify apostrophes/quotes). Exact hit → MATCH; normalized-equal → **LIKELY MATCH** (own chip: "case/punctuation differs — confirm", both strings shown — normalization is a policy call the tool surfaces, not silently decides); no acceptable hit → MISMATCH.
  - ABV — three-band comparison (cross-model synthesis, Rev 2.1): exact match at stated precision → **MATCH** (green). Differing but within the commodity band → **WITHIN TOLERANCE — confirm** (amber, LIKELY-MATCH family, never green; evidence crop mandatory; granted only when digit-level OCR confidence is high, else NEEDS REVIEW). Outside the band or across a class boundary → **MISMATCH**. Bands (magnitude heuristics): wine ±1.0pp >14% / ±1.5pp ≤14% (§4.36, tier selected by the label-stated value); spirits ±0.3pp (§5.65(c)); malt ±0.3pp (§7.65(c)). **Legal grounding stated honestly**: the CFR tolerances govern label-vs-actual product, not label-vs-application — the warrant for tolerating drift is Form 5100.31 allowable-revision item 11 (ABV statement may change without a new COLA), with the CFR bands used only as the magnitude reference; the UI note cites both. Override table (no band ever rescues): wine class breaks at 14/21/24%; "non-alcoholic" 0.5% (zero tolerance, adjacency statement required); malt "low/reduced alcohol" hard cap 2.5%; sub-0.5% products at 0.01 precision, zero tolerance; malt stated to nearest 0.1. Range labels ("Alcohol _% to _%"): parsed; application value inside the range → amber confirm; spread-limit check (2pp/3pp wine tiers) is a cited P3 rule. Within-band digit-misread cases (3/8, 5/6, 0/9 confusables) join the golden set and **ABV false-MATCH rate is its own M0 metric**.
  - Net contents: regex value+unit (750 mL, 0.75 L, 25.4 fl oz) with unit conversion.
  - ABV↔Proof label-internal cross-check: when the label states both, verify proof = 2 × ABV; disagreement → dedicated "Label internal consistency" MISMATCH row showing both parsed values.
  - Government warning — three sub-results, not one: **anchor** the `GOVERNMENT WARNING` text block, then check **text** (normalize whitespace only; exact compare against the 27 CFR 16.21 statutory text; word-level diff on mismatch — whitespace tokenization, case-sensitive token compare), **prefix caps** (all-caps asserted from raw OCR output, its own line), and **weight contrast — two-sided requirement per §16.22(a)(2)** (prefix must be bold AND body must NOT be bold — an all-bold warning is also a violation). The stroke-width heuristic measures prefix-vs-body contrast and reports three outcomes: `contrast OK` / `no contrast — violation, side indeterminate ("confirm which side")` / `unknown → confirm visually`. **No side ever passes solely from the heuristic**; each direction has its own M0 kill-gate, validated only on printed-and-photographed samples (never raw synthetic renders). Type size (1/2/3mm by container), characters-per-inch caps (40/25/12), placement, and contrast documented as not checked, each with its §16.22 citation.
  - Fields with no application data are **NOT CHECKED** and excluded from overall status.
- **Visual provenance** (unlocked by OCR bounding boxes — both outside voices called this the highest-trust feature): every field verdict shows the actual image crop it was read from, so agents distinguish faithful reads from OCR errors at a glance.
- **Per-field verdicts**: MATCH / LIKELY MATCH (incl. WITHIN TOLERANCE) / MISMATCH / NEEDS REVIEW / NOT CHECKED / **NOT REQUIRED** (grey informational, Rev 2.1: application supplied a value but the label legally omits the field — e.g., ABV on ≤14% "table"/"light" wine, cross-checked against the label's Class/Type result; or "not required federally — confirm" for malt where flavored-alcohol status and state law are unknowable; excluded from the worst-of fold, rendered with its citation). NEEDS REVIEW always carries a reason code — `unreadable` (low OCR confidence), `absent from label`, or `system error` — each demands a different agent action. Overall status is worst of the checked fields. **Framing**: screening assistant — the all-clear state reads "All checks matched — ready for agent sign-off", never an approval verdict.
- **Batch mode**: multi-file drag-drop; per-file inline application data is the primary path ("apply to all" only for genuinely shared fields), CSV manifest mapping `filename → application record` as the power-user path. Items process independently at bounded concurrency: a failed item never blocks the batch and is individually retryable; cancel stops unstarted items; navigating away mid-batch warns. Local OCR at ~1-2s/label × concurrency 4 ≈ 300 labels in ~2 minutes, rows streaming in as they complete.
- **UI**: one screen, specified in detail in "UI Specification" below. No settings, no navigation.

## UI Specification (added by design review — cross-model synthesis)

**Classification: APP UI** (task-focused operational tool). Branding quiet; dense, stable, familiar controls; evidence never hidden behind hover, animation, or color alone.

**Three permanent regions, master-detail:**
1. **Start a check** — upload (visible "Choose files" button — drag-drop is never the only mechanism), "Try a sample", CSV manifest import. Collapses to a compact "Add more files" control once files exist.
2. **Applications** (batch list, left pane) — one row per file: filename, compact status lozenge, inline application fields (collapsed row shows brand + status; expand to edit all four). Rows never auto-reorder as results stream in (spatial memory + keyboard focus stability); filters "Needs attention / In progress / All" with counts; progress as exact counts ("18 of 42 checked").
3. **Selected label** (detail panel, right) — label image with evidence crops, overall screening summary, field comparisons in fixed checklist order: Brand → Class/Type → ABV → Net Contents → Internal Consistency → Government Warning. Batch rows summarize; selection reveals detail — never 300 expanded records.

Single-label mode is the same structure with a one-item list auto-selected. Explicit on-screen headings ("Start a check", "Applications", "Selected label") make the page scannable by headlines. Quiet product identity line (name + "TTB label screening — prototype") so the first screen is unmistakable.

**Form (single or per-row)**: beverage-type selector FIRST (Wine / Distilled Spirits / Malt Beverage / Not specified — required record metadata; "Not specified" applies the strictest band ±0.3 with a "commodity not specified" note, routes absent-ABV to confirm-visually, and does not satisfy the empty-form check; changing it marks commodity-dependent results stale for Re-check), then Jenny's printed checklist in fixed order — Brand Name, Class/Type, Alcohol Content, Net Contents. The selector flows through batch per-row editing, "apply to all", the CSV manifest (`beverage_type` column with enum validation + T9 test rows), and the export. Government Warning check is always-on and automatic (statutory constant, no input). Verify with empty form prompts inline: "Enter at least one field to check — the Government Warning is always checked." Strict tab order, Enter submits, values persist across labels ("Check another label" clears image, keeps form). Editing a field after results marks that row's result stale with an explicit "Re-check" action (no silent auto re-verification). "Apply to all" shows a confirmation naming the field, value, and affected-file count, and supports undo.

**Overall status — two axes, precedence defined.** Screening result: `mismatch found` / `no mismatch found` / `screening incomplete`. Attention state: `action required` / `none`. Field precedence for the summary: MISMATCH > NEEDS REVIEW > LIKELY MATCH > MATCH; NOT CHECKED excluded; a system error marks the record `screening incomplete` while **preserving completed field results** (a timeout never converts finished checks into a blanket failure). All-NOT-CHECKED records read "Nothing to check yet — enter application data."

**Absent is not automatically NEEDS REVIEW**: a readable label confidently searched with no hit for a required field is a potential MISMATCH ("Expected text was not found — inspect the full label"); only low OCR confidence yields NEEDS REVIEW (unreadable). The unreadable/not-found boundary is explicit in the rules engine.

**Banner copy per state (exact strings):** all matched → "All checks matched — ready for agent sign-off" (icon must not resemble a regulatory approval seal); mismatches → "{n} field(s) don't match the application — see {fields} below"; needs review → "{n} field(s) need your eyes — see {fields} below"; mixed → mismatch sentence then review sentence; likely-only → "Everything matches, {n} small difference(s) to confirm"; incomplete → "Some checks didn't finish — retry below."

**Every non-match chip carries next-action language**: LIKELY MATCH "Capitalization or punctuation differs — compare both values"; MISMATCH "Application and label differ"; NEEDS REVIEW(unreadable) "Couldn't read this part of the image — check the label yourself or upload a clearer photo"; NEEDS REVIEW(system) "This check didn't finish — retry"; NOT CHECKED "No application value entered."

**Verdict presentation**: 5 states in data, 3 visual families on screen (green / amber "you decide" / red; NOT CHECKED grey, de-emphasized). Compact icon+word lozenges at field level — status must never be louder than the mismatched values; the large treatment is reserved for the overall banner (the verdict anchor; the label image anchors the evidence panel). Color+icon+word always together.

**Evidence crops**: ≥64px thumbnail height, click-to-enlarge into an accessible dialog showing the crop's location outlined on the full label image; never hover-only. No bounding box → verbatim text fallback with "no image region available."

**Government warning — a grouped check, not one row**: one-line summary + three labeled subchecks (Text exact / ALL-CAPS prefix / Weight contrast — prefix vs body), evidence crop, differences revealed by a button (not permanently expanded) using labeled language — "Expected", "Found", "Different capitalization", "Missing word" — with one plain sentence ("The label says 'birth defect' where the required text says 'birth defects'."), never red/green-only or strikethrough-only. Persistent note listing what is NOT checked (type size, placement, contrast).

**Errors are inline, persistent, adjacent to their cause — never toasts.** Distinct copy per class (unsupported type, oversized, corrupt image, CSV format, filename mapping, server busy with honest expectation, OCR failure, timeout, network, export failure), each with a recovery action and preservation of entered data. Loading stages in plain words, three max: "Reading the label… / Checking fields… / Almost done" + elapsed seconds. Item states named: Waiting / Uploading / Ready / Queued / Checking / Complete / Canceled / Could not finish. Cancel is labeled "Cancel waiting checks" (it does not interrupt in-flight items). "Results are stored only in this browser tab" is visibly stated near Export, not buried in an exit warning.

**Batch completion state**: "Done: {matched} matched, {review} need review, {mismatch} mismatched" with one-click filter to non-green rows; Export lives here. Empty states specified for: no files; files without data; manifest with zero matches; filter with no results — each warm, with a primary action.

**Evaluator narrative — samples are named proof points**: the sample chooser lists five described examples — clean match / obvious mismatch / title-case warning trap / bad photo routed to review / small batch showing independent progress and one failure. A silent single-sample demo button wastes the strongest proof.

**Print**: print-friendly single-label report (crops included) — Dave prints his emails; CSV is Jenny's format. (M4)

**UI constants** (numbers are the requirement): base font 18px (16px floor anywhere); chip text 16px bold; inputs ≥48px tall; targets ≥44×44; line length ≤72ch; spacing scale 8px; one accent + three verdict colors, WCAG 2.2 AA contrast incl. deuteranopia check; visible keyboard focus ≥3:1 against adjacent colors; one real typeface (Public Sans — USWDS face); 200% zoom without clipped actions. Motion: in-place streaming updates and staged progress only; `prefers-reduced-motion` honored; no decorative animation.

**Accessibility is M1 architecture, not M4 polish**: native buttons/inputs, programmatic labels, logical focus order stable during streaming, focus moves to first actionable error, restrained live regions for status changes (never per-row announcements), accessible dialog for crop zoom, keyboard-only + screen-reader test before ship. M4 is the audit.

**Hard-rejection guardrails (implementer "don'ts")**: no card-inside-card layouts; no status-chip wallpaper; no dashboard stat-cards before the work; no giant persistent drop-zone hero; no responsive-by-stacking a desktop table; no mystery icon-only actions (retry/cancel/enlarge/export get text labels); no accordion-hiding of critical mismatches; no auto-reordering while processing; no shadow-based hierarchy. Cards only for the overall summary and the warning group.

**Responsive intent**: desktop-first master-detail with fixed-width list pane; <900px stacks regions sequentially with a sticky selected-label summary and explicit "Back to applications" control preserving selection and scroll; crop + label value + application value never compress into three columns — they stack in the order "Label evidence" then "Application value"; status and actions never depend on horizontal scroll. Mobile is functional, not optimized.

## Stack

- **FastAPI (Python) + PaddleOCR + OpenCV** backend and **Next.js/React** frontend, shipped as **one Docker image**, deployed on Fly.io or Render (Vercel serverless can't run native OCR). `docker compose up` runs the whole thing on a laptop — which *is* the firewall story: this exact image runs inside TTB's network with zero code changes. No API keys anywhere.
- **OCR behind an `Extractor` interface** so an engine swap (tesseract.js client-side, or a future on-prem VLM) is a drop-in, not a rewrite.
- **Abuse protection on the public URL**: per-IP rate limit, image size cap (reject >8MB pre-upload), request validation, graceful "service busy" state. (No quota-burning API key to protect — local compute only.)
- **No database**: stateless prototype, nothing stored. Results live in the browser session; CSV export is the record.
- **Tests**: pytest for the rules engine + parsers (the deterministic core), plus the golden-set eval harness from M0 for the OCR pipeline.

## Latency budget (5s hard target)

- **What "5 seconds" means**: p50 from clicking Verify to rendered field results, on the deployed URL, warm path. The ~10s ceiling is outlier error handling, not acceptable latency. Measured p50/p95 published in the README, not asserted.
- Client image downscale capped conservatively (longest side ~2000px, high quality) — aggressive compression destroys the small warning text the tool exists to read; M0 validates the size against small-text golden labels.
- PaddleOCR on CPU: ~1-2s per label image; preprocessing ~200ms; rules engine <1ms. Deterministic — no network variance, no provider queueing, no cold-start model loads (model warmed at container boot).
- Progress indicator with elapsed time; >10s → NEEDS REVIEW (`system error`) with a retry button.

## Milestones

0. **M0 — Feasibility spike (half a day, before any UI)**: script running the OCR pipeline against ~8 representative labels (clean, small-text, skewed, glare, curved bottle, decorative font, title-case warning trap, word-substitution trap, all-bold warning trap [printed-and-photographed], within-tolerance ABV digit-misread pair) reporting per-field read fidelity + latency for PaddleOCR vs tesseract.js. Proves or breaks the riskiest premise (OCR fidelity on stylized label typography) first; if both engines fail the golden set, the fallback conversation happens before UI work. The spike script becomes the permanent eval harness.
1. **M1 — Core verify loop**: single-label upload + form → OCR → rules engine → results panel. Includes minute-one failure modes: file-type/size validation, non-label image → NEEDS REVIEW with a plain message, OCR/system-failure and timeout states, and a "Try a sample" demo button (bundled labels: clean match, deliberate mismatch, bad photo — prefilled data). Deployed.
2. **M2 — Verification hardening**: statutory warning anchor + exact-match + word-level diff, prefix-caps and weight-contrast checks, commodity-aware ABV rules (three-band comparison, override table, NOT REQUIRED disposition, beverage-type selector plumbing incl. CSV/contract), per-field evidence crops (bounding boxes), ABV/net-contents parsers, ABV↔Proof cross-check, normalization rules, unit tests, adversarial golden set (AI-generated labels incl. the title-case and word-substitution traps).
3. **M3 — Batch mode**: multi-upload, per-file inline data with "apply to all" for shared fields, CSV manifest path, concurrent processing, results table + CSV export.
4. **M4 — Polish**: accessibility pass (keyboard, contrast, large text), remaining empty/loading states, README (setup, approach, assumptions, trade-offs, measured p50/p95, firewall/on-prem story), sample labels in repo.

## Non-goals

- COLA integration, auth/user accounts, persistence, PII handling.
- Full TTB rulebook beyond core field checks — documented limitation. (Rev 2.1: core commodity awareness — tolerances, ABV requiredness, molded-glass caveat — is now IN scope at M2; standards of fill, appellations, age statements, and deeper type rules remain out.)
- Cloud ML assistance of any kind (user decision at premise gate) — a future *optional* VLM assist for hard photos would sit behind the `Extractor` interface and is listed in TODOS.md, not in scope.

## Assumptions

- Application data is entered/uploaded by the agent (no COLA feed).
- One image per label application; front/back merging deferred (TODOS.md) and the single-image assumption stated in the README as a scoping choice.
- Weight-contrast detection compares the anchored prefix crop against the warning body (three outcomes, Rev 2.1); `unknown`/indeterminate yields "confirm visually", never a failure.
- English-language labels only for the prototype.
- OCR fidelity on decorative typography is the load-bearing risk, and it is *measured at M0*, not assumed: script-font brand names that OCR misreads route to NEEDS REVIEW (with the evidence crop shown) rather than false MISMATCH — the honest degradation path.

---

## Engineering Hardening (Phase 3 additions — eng dual-voice findings, auto-approved)

**Deployment reality (A1-A3):**
- Worker pool sized from **measurement, not estimate**: each PaddleOCR worker is ~400-700MB RSS; M0's exit criteria include per-worker memory and per-label latency **on the target instance type** (Fly/Render shared vCPUs run 3-8s/label — a laptop benchmark proves nothing about the 5s requirement). Instance size and monthly cost land in the README from that measurement. Default posture: 2 warmed workers + bounded queue; single-worker fallback documented.
- **Frontend ships as static export** (`output: 'export'`) served by FastAPI StaticFiles — one process, one port, no Node runtime, no supervisor. Next.js remains the build toolchain only. Image budget: multi-stage build, `opencv-python-headless`, models baked; check platform image-size limits (paddle stack is 2-4GB naive).
- Client-side downscale to ~2000px is **mandatory before upload** (enforced, not best-effort) — the 300-label batch math dies under 8MB originals.

**Load behavior (A4-A5):**
- Timeout-kill of a worker triggers a warmed respawn; capacity sheds load (429) during reload instead of queueing into a death spiral. Max-requests-per-worker recycle policy guards paddle memory growth.
- Fairness: single verifies take priority over batch items (two-priority queue) and per-client in-flight is capped at 2 — one importer's 300-label dump must not blow another agent's 5s budget.

**OCR-reality edge cases (E1-E6):**
- **EXIF orientation applied at decode** (`ImageOps.exif_transpose`) + PaddleOCR angle classifier for 180°; rotated images added to the golden set.
- **Text-mass gate before the rules engine**: below a token/area floor, the whole record is NEEDS REVIEW ("this doesn't look like a label") — the absent→MISMATCH rule applies only past this gate (kills the cat-photo-as-confident-MISMATCH contradiction).
- **Warning anchors: locate all candidates, evaluate each, best candidate wins** (pass if any passes); evidence crop shows which region was used.
- **Warning region quality gate**: blur/contrast metric on the warning crop (not just word confidence — OCR misreads are often high-confidence) routes bad regions to NEEDS REVIEW(unreadable) before diffing. M0 reports **warning-paragraph exact-match rate on clean images as its own pass/fail number** — the flagship check must not cry wolf on OCR error.
- **Conditional preprocessing**: run raw first; apply deskew/contrast pipeline only when raw confidence is poor (or best-of-two). Adaptive thresholding on clean images lowers PaddleOCR accuracy — M0 measures raw vs preprocessed per golden label.
- **HEIC/WebP accepted** via Pillow plugins (iPhone photos are the natural input); if registration fails, the error names the fix ("iPhone photos: export as JPG").

**The locator is a named component, not a bullet (H1, H3):** box→line grouping by y-overlap, line→block reading order, sliding token-window search with per-window scores, cross-line join (stacked brand names like "STONE'S\nTHROW" are the NORMAL case), hyphenation handling; warning block reconstruction grows from the anchor by line adjacency until the token stream covers the statutory length. Unit-tested against **synthetic box layouts — no OCR needed in locator tests**.

**Fuzzy matching pinned (T1):** rapidfuzz `token_sort_ratio` on normalized strings, threshold 90, windows sized ±1 token of the expected length; high-fuzzy-but-not-normalized-equal is **MISMATCH with both values shown, never LIKELY MATCH** ("OLD TOM DISTILLERY" vs "OLD TOM DISTILLING CO." must fail); boundary test table (just-above/below threshold, short brands like "VOX", brand-inside-class-type).

**Bold heuristic is relative, not absolute (H2):** prefix stroke ratio compared against the rest of the warning paragraph on the same label; ambiguous bands → `unknown`. Precision over recall — a confident wrong answer is worse than "confirm visually".

**Batch client is an explicit state machine (H5):** reducer with unit tests for edit-during-checking, retry-after-cancel, undo-apply-to-all-after-partial-completion. The "no state machines" claim in Section 5 is retracted for the batch client.

**Security invariant (S1-S3):** OCR-derived text is attacker-controlled (an image can OCR into `<img onerror=...>` or `=HYPERLINK(...)`) — it renders via element construction/text nodes only, never innerHTML, in the diff, the print report, and every export. Rate limiting reads the platform's canonical forwarded header only (never client-supplied X-Forwarded-For) plus a global concurrency ceiling; multipart read timeouts, response crop count/size bounds, and max lengths on all echoed string fields.

**Added tests (T3-T5):** load test at 3× pool concurrency asserting clean 429s and no cross-request bleed; CSV manifest suite (UTF-8 BOM, CRLF, semicolon delimiters, quoted commas, duplicate rows, missing/extra columns, 10k-row cap); ABV grammar confusables ("%" misread), trailing-zero precision semantics, proof-only labels converted for comparison.


## Engineering Hardening II (Codex eng voice deltas — auto-approved, cross-model)

**Process topology is explicit:** one API process; one shared OCR pool of measured size (never per-web-worker pools); pool size from CPU **quota** (cgroup-aware), not `os.cpu_count()`; native thread pinning (`OMP_NUM_THREADS=1` etc.) so N workers ≠ N×threads oversubscription. Static-export frontend already removed the two-server supervisor problem; `/healthz` asserts a live warmed worker, not just model init.

**Worker supervision is a design, not a flag:** dedicated long-lived worker processes with task IDs; hard-terminate-and-replace semantics (canceling a future does NOT stop native Paddle inference); crash-loop limits; **queue timeout and execution timeout are separate numbers** — a healthy job never fails because the pool was busy; it reports "waiting" truthfully.

**Batch becomes an in-process job API** (submit/status/result/cancel) instead of 300 synchronous requests: enables true cancellation of server-queued items ("Cancel waiting checks" now matches reality), fair two-priority scheduling, truthful progress counts, and clean Retry-After backoff (client respects it; no synchronized retry storms). No external queue infra — in-process only. Stateless fragility stated honestly: results live in the tab; refresh/crash loses batch continuity (documented as a prototype limitation in README and near Export).

**Evidence is coordinates, not payloads:** the API returns bounding boxes + region-quality metrics; the browser retains the uploaded file and renders crops client-side (canvas). Kills base64-in-JSON bloat, multi-GB batch sessions, and GC pauses; object URLs cleaned up; response sizes bounded.

**Locator spec (deepened):** line clustering from quadrilaterals with permitted gap bounds; reading-direction and orientation handling; max token span; duplicate/overlapping detection resolution; **per-field, length-calibrated thresholds** (a 3-char brand and a 5-word class/type cannot share one number) with an **ambiguity margin** — if the second-best candidate scores within the margin, the field is NEEDS REVIEW with both candidates shown, never a silent pick; candidate provenance includes the full source span + surrounding context (a "750 mL" inside multipack marketing copy must not satisfy net contents).

**Absence requires coverage, not confidence:** high confidence on detected words says nothing about undetected text. `absent → MISMATCH` applies only when the text-mass/coverage model supports "this region was adequately observed"; otherwise the verdict reads **"not found in the submitted image"** (NEEDS REVIEW), and the single-image limitation stays prominent. This supersedes the Phase 2 absent-split where coverage cannot be established, and resolves the error-table/design contradiction (anchor-not-found row now follows the same policy).

**Warning check honesty (supersedes "verbatim by construction" phrasing):** OCR is probabilistic transcription; the comparison is exact but its input is not. Three outcomes: **verified match** (every glyph well-evidenced), **definite mismatch** (image evidence supports the differing glyphs — one-char legal mutations distinguished from one-char OCR confusables I/l/1, O/0 at character level, not word level), **unable to verify** (uncertainty could explain the difference). M0 measures warning-paragraph exact-match rate as its own gate; the golden corpus separates real photos from synthetic renders and includes OCR-error-vs-label-error discrimination cases.

**Statutory constant provenance:** authoritative source (§16.21 verbatim from eCFR, effective version recorded) + the §16.22 format matrix carried alongside; checksum test guards editorial drift; the exact set of legally-neutral normalizations is enumerated (whitespace collapse only; NFC documented as applied to *search text*, never to the statutory constant).

**Bold heuristic has an M0 kill-gate:** relative same-label comparison as specified, but if measured precision is poor, the feature ships as always-"confirm visually" — a confidently wrong bold verdict is disqualifying, an honest unknown is not. Synthetic labels are excluded from validating this heuristic.

**Latency honesty:** README publishes cold-start p50, warm p50/p95, queue-inclusive latency, and batch time-to-first-result / time-to-completion — not just a warm p50. The 5s budget explicitly includes client resize, upload, queue wait, response transfer, and render.

**Deployment is one named platform, validated:** Fly.io (always-on machine, predictable CPU quota); M0 measures compressed image size, cold boot + warmup vs platform health-check deadlines, steady/peak RSS per worker incl. 40MP decode, and throughput under the real CPU limit, using the exact production image on the exact VM class.

**Privacy/logging:** logs carry request IDs, stage timings, and verdict *statuses* — never raw OCR text, field values, or image bytes; exception traces scrubbed; multipart temp files cleaned on request end; platform log retention noted in README.

**Eval corpus split:** demo samples (5 named proof points) ≠ evaluation corpus. M0 calibration set ≈ 25-30 images (real photos + synthetic, separated), reporting false-positive/false-negative rates per field — thresholds are tuned on this set, and "never a false PASS" claims are scoped to what the corpus actually establishes.

### Eng Dual Voices — Consensus Table
```
  Dimension                          Claude   Codex    Consensus
  ─────────────────────────────────  ───────  ───────  ─────────────────────────
  1. Architecture sound?             shape ok topology CONFIRMED after fixes
                                     deploy─  gaps     (topology, job API, static export)
  2. Test coverage sufficient?       gaps     gaps     CONFIRMED after additions
  3. Performance risks addressed?    5s vs HW 5s def'n CONFIRMED after fixes (M0 on target, honest metrics)
  4. Security threats covered?       XSS/IP   logs/PII CONFIRMED after additions
  5. Error paths handled?            E2 gate  timeout  CONFIRMED after fixes (absent policy unified,
                                              semantics queue vs exec timeout split)
  6. Deployment risk manageable?     unproven unproven CONFIRMED after fixes (one platform, measured M0)
```
No cross-model disagreements survived — the voices converged on every load-bearing item; Codex's "exact-match overstates what is proven" correction was accepted as a wording+model fix, not contested.

### Test Coverage Diagram (Phase 3)
```
CODE PATHS                                          USER FLOWS
[+] api/locator (named component)                   [+] Single verify
  ├── [PLANNED ★★★] line grouping / reading order     ├── [PLANNED ★★★] happy path E2E (sample → <5s)
  ├── [PLANNED ★★★] cross-line join, hyphenation      ├── [PLANNED ★★ ] empty-form prompt
  ├── [PLANNED ★★★] threshold boundaries + margin     └── [PLANNED ★★ ] error states (type/size/corrupt)
  └── [PLANNED ★★★] synthetic-layout corpus         [+] Batch
[+] api/rules                                         ├── [PLANNED ★★★] partial failure + per-row retry
  ├── [PLANNED ★★★] parsers (ABV/proof/net, confus.)  ├── [PLANNED ★★ ] cancel waiting checks (job API)
  ├── [PLANNED ★★★] warning 3-outcome + char-level    ├── [PLANNED ★★ ] apply-to-all undo after partial
  ├── [PLANNED ★★★] statutory checksum guard          └── [PLANNED ★★ ] manifest error repair flow
  ├── [PLANNED ★★★] overall precedence + NOT CHECKED [+] Evaluator flow
  └── [PLANNED ★★ ] coverage/text-mass gate           └── [PLANNED ★★ ] five named samples walk-through
[+] api/ocr_pool                                    [→EVAL] M0 harness: per-field fidelity, warning
  ├── [PLANNED ★★ ] queue vs exec timeout                    exact-match rate, FP/FN curves, raw-vs-
  ├── [PLANNED ★★ ] worker recycle / crash-loop              preprocessed, bold precision kill-gate
  └── [PLANNED ★★ ] load: 3× pool → clean 429s
[+] web/batch reducer
  └── [PLANNED ★★★] edit-during-check, retry-after-cancel, undo interactions
GAPS (Rev 2.1): commodity-aware rules, selector plumbing, contract amendments, and new golden cases added as tasks T11-T13 below; all other paths remain named milestone deliverables (M0-M3)
```

### Worktree Parallelization Strategy (Phase 3)
| Step | Modules touched | Depends on |
|---|---|---|
| M0 spike + eval harness | api/eval/ | — |
| Locator component | api/locator/ | M0 (engine choice) |
| Rules engine + parsers | api/rules/ | — (pure functions, testable standalone) |
| OCR pool + job API | api/ocr_pool/, api/jobs/ | M0 (sizing) |
| Web UI (master-detail, states) | web/ | API contract (types only) |
| Docker/deploy | Dockerfile, fly.toml | M0 (sizing) |

Lanes: **A**: M0 → locator → pool/jobs (sequential, shared api/). **B**: rules engine + parsers (independent, pure). **C**: web UI against a mocked API contract (independent). **D**: Docker/deploy after M0. Launch B + C parallel with A; merge; D last. Conflict flag: A and B both touch `api/` — keep `api/rules/` isolated from `api/locator/` imports (one-way dependency: locator → rules types only).


## Developer Experience Specification (Phase 3.5 — cross-model synthesis)

**Two run paths, both first-class:**
- **Evaluator path (default)**: `docker compose up` pulls a **prebuilt image from GHCR** (built by CI on every push); `--build` is the from-source fallback. This turns a 10-25 min cold paddle build into a ~2-4 min pull. Published up front: image download size, minimum RAM (4GB Docker allocation), disk, architectures (amd64+arm64), expected startup time. TTHW split honestly: deployed URL <1 min; clone path <5 min of developer interaction (download time reported separately).
- **Contributor path (no Docker)**: documented `pip install -r api/requirements.txt && uvicorn api.main:app` (with the paddle-is-heavy caveat) + `npm run dev` proxying to :8000 — the frontend iteration loop exists even though production ships a static export.

**Startup diagnostics get the same care as runtime errors:** README troubleshooting table keyed by symptom — exit 137 (OOM: raise Docker memory or `OCR_WORKERS=1`), port in use (`APP_PORT=8001`), Docker missing/daemon stopped, slow first boot ("Loading OCR models — up to N seconds", visible via `/healthz` states: alive → loading models → ready → degraded). Port pinned to 8000 with a "ready at http://localhost:8000" log line after warmup. Single-worker fallback is a documented env var, not a deployment footnote.

**API contract pinned now (resolves the plan's own two conflicting sketches):** `POST /api/verify`, multipart `image` (binary) + `application` (JSON string, documented schema). Response envelope:
```json
{"schema_version":"1","request_id":"…","screening_result":"mismatch_found","attention_state":"action_required",
 "timing_ms":{"total":1842,"ocr":1620,"rules":3},
 "fields":[{"field":"brand_name","status":"MISMATCH","label_value":"…","application_value":"…",
            "reason_code":"value_differs","evidence":{"bbox":[100,120,420,190],"region_quality":0.91}}]}
```
Rev 2.1 contract amendments (made pre-M1, schema_version stays "1"): `application` JSON gains required `beverage_type` (`wine|distilled_spirits|malt_beverage|unspecified`); status enum gains `NOT_REQUIRED` and `WITHIN_TOLERANCE`; reason codes gain `within_tolerance_confirm`, `not_required_for_commodity`, `not_visible_in_image`, `commodity_unspecified`.
```json
```
Machine reason codes are separate from display copy. Evidence is coordinates (client crops from its retained file). Zero-field curl request → 200 with warning-only results (documented). Status enum spelling pinned (`MATCH|LIKELY_MATCH|MISMATCH|NEEDS_REVIEW|NOT_CHECKED`). FastAPI `/docs`, `/redoc`, `/openapi.json` stay enabled (static mount must not swallow them — acceptance criterion) and the README carries one tested copy-paste `curl -F image=@samples/clean.jpg …` example. Batch is client-orchestrated via the job API — stated explicitly so nobody hunts for `/api/batch`.

**README is an M1 exit criterion, not M4** (it is a graded deliverable and the first thing the evaluator reads): M1 ships setup + run + curl + 6-line architecture argument + sample walk-through; M4 is the polish pass (measured numbers, trade-offs). Two-minute skim order: what it does (screenshot) → one-command run → five samples → architecture → why rules-not-LLM issue verdicts → measured latency with hardware context (commit, CPU, workers, dataset; estimates labeled as estimates until M0 data lands) → limitations → test commands → on-prem notes.

**Named commands:** `make test` (deterministic units, no model, <30s), `make eval` (golden set in the image, machine-readable + markdown results), `make smoke` (start built container, wait ready, one /api/verify, exit — used by CI as the clean-machine clone-to-result proof), `make lint`.

**Reproducibility:** locked Python + npm dependencies; base image pinned by digest; OCR models vendored/fetched by checksum at build (never at runtime — enforced by an automated **no-egress test** in CI, which is also the firewall story made testable); golden-set expected metrics versioned with tolerated ranges; sample/golden images committed at M0 under `api/eval/golden/` with provenance + licensing notes (AI-generated, redistributable).


---

## Research Integration (Revision 2 — 2026-07-31, /autoplan cycle 2)

Fourteen research documents (`docs/research/`) were folded into this plan. Auto-approved changes:

**Regulatory correctness (from `ttb-labeling-rules.md`, eCFR primary text):**
- ABV tolerances and class-boundary overrides now in the rules engine (edit above) — the highest-impact correction of the cycle; the prior rule false-MISMATCHed compliant labels.
- Two-sided bold check on the warning (prefix bold, body not-bold), with an all-bold adversarial golden case added to the M0 corpus.
- **Commodity awareness enters M2 scope (reverses a gate decision — see gate item):** a beverage-type selector (wine / distilled spirits / malt) drives (a) which ABV tolerance applies, (b) whether a missing ABV is compliant (optional on ≤14% "table"/"light" wine and unflavored malt) vs a finding, and (c) phrasings for the sulfite/aspartame checks — which are **informational presence-observations outside the verdict fold** (the application carries no SO₂/aspartame data, so they can never be verdicts). Without the selector, absent-ABV dispositions are wrong for two of three commodities.
- Net contents may be legally molded into the glass (spirits/malt only — §5.70/§7.70; wine has no such caveat) — absent net contents routes to "not visible in the submitted image"/unverifiable **unless coverage provenance establishes a full-container view**; a finding is possible only past that gate (codex refinement — blanket "never MISMATCH" was itself a false-PASS channel).
- ABV-statement format checks (three authorized sentence shapes, §5.65(b)/§7.65(b)) added as cited P3 rules.

**Input-distribution facts (from `cola-fact-sheet.md`, TTB's own filing specs):**
- The M0 corpus and upload path now target TTB's stated input distribution: JPEG/PNG only, ≤1.5MB per label image, 120-170 dpi at "Medium" JPEG quality, cropped to label edges — our caps and downscale settings validated against the agency's own numbers.
- **Per-panel uploads are the norm in real filings** (brand/back/neck each a separate file): the single-image assumption is restated as the prototype's loudest limitation, and the multi-image TODO moves to the top of the P2 queue.
- Allowable revisions (Form 5100.31 items 1-24) mean a bottle may legitimately differ from its registry label in shape, color, fonts, ABV statement, net contents, and address — documented in the README as *why* field-by-field comparison with per-field rules is the only sound verification model.

**Product framing (from `cola-swot.md`, `cola-prescreen-market.md`, strategy playbooks):**
- README strategic paragraph gains three beats: (1) this is Treasury's own named priority use case ("document processing and regulatory intake", Treasury AI Strategy, Sept 2025); (2) TTB's own FAQ admits consistency "can be addressed only to a limited degree by a Web-based system" — the official warrant for deterministic, citation-backed checks; (3) the open-stack build is the seed of a public screening commons (nationalize-by-absorption) rather than a private toll booth.
- **Demo narrative updated:** the batch proof point becomes "post-shutdown Monday — 300 queued labels triaged before lunch" (Oct 2025 shutdown, 85% of TTB furloughed, Q4 = 30-40% of craft-spirits sales), with Janet's importer as secondary framing.
- Per-field regulatory citations (requirement basis + section + ttb.gov link per check) confirmed as the underserved differentiator — P2, first in queue after ship-blockers.

**Revision 2.1 — dual-voice review of this revision (Claude 19 findings, Codex 10; full convergence on the top item):** the tolerance rule as first drafted was a category error — CFR tolerances govern label-vs-actual product, not label-vs-application — and created a false-PASS channel (OCR digit misreads landing inside ±1.5 turning real errors green). Fixed with the three-band model: exact→green, within-band→amber confirm (never green, digit-confidence-gated), outside→red; legal warrant restated as allowable-revision item 11 with CFR bands as magnitude only. Bold collapsed to a three-outcome contrast model (no side passes from the heuristic alone; per-direction kill-gates; printed-photo validation). NOT REQUIRED added as a sixth disposition with the wine table/light cross-check. Selector specified end-to-end (form-first, Not-specified default, CSV column, contract amendment, stale-on-change). Net-contents absence coverage-gated. Consistency debt cleared (stale test specs, error-map supersession, coverage-diagram claim, Non-goals line).

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 35 | Rev2 | Commodity awareness into M2 (reverses gate decision) | **User ratification required** | P1 | Regulatory correctness: absent-ABV wrong for 2 of 3 commodities without it |
| 36 | Rev2 | ABV three-band model (exact/amber-band/red) | Mechanical | P1 | Both voices: green tolerance-MATCH was a false-PASS channel; category error on CFR grounding |
| 37 | Rev2 | Bold → three-outcome contrast model | Mechanical | P5 | Both voices: per-side attribution exceeds what the heuristic measures |
| 38 | Rev2 | NOT REQUIRED disposition + coverage-gated net-contents absence | Mechanical | P1 | Codex: blanket never-MISMATCH was itself a false-PASS channel |

**Doctrine checks (failure/success playbooks — confirmations, no changes):** the plan already sits at the documented intersection — measured slices (M0 gates, CI assertions), humans deciding (screening-only authority), open components behind an interface (national AI Action Plan preference), federated-tier compliance shape (Treasury strategy), evals-as-gates (Palantir/NIST doctrine), and the Algorithm's ordering (requirements questioned at the premise gate before anything was optimized).

---

# Review Record (/autoplan, 2026-07-31)

## Step 0 — CEO Scope Challenge (Mode: SELECTIVE EXPANSION)

### 0A Premise Challenge (user-confirmed at gate, with one reversal)
- **P1: The core problem is field matching, not judgment.** Grounded in Sarah's interview. Confirmed — LLM-free rules engine decides; humans get NEEDS REVIEW.
- **P2: The real customer of this deliverable is the evaluator.** Confirmed — demo button + failure states are M1, not polish.
- **P3: ~~Cloud vision API acceptable for prototype~~ → REVERSED BY USER: local/OCR, firewall-native, no cloud ML API.** The pipeline must run on infrastructure we control end-to-end.
- **P4: 5 seconds is a hard adoption threshold.** Confirmed — and now met deterministically (local CPU inference, no network variance).

### 0C Dream State
```
CURRENT STATE                    THIS PLAN                        12-MONTH IDEAL
Agents eyeball 150k         --> Prototype: per-field verify   --> Full CFR rules engine w/
labels/yr against forms         in <5s local OCR, batch mode,     citations, COLA workflow
manually, 5-10 min each         evidence crops, deployed demo     integration, on-prem at TTB
```
Delta: the local architecture moves *toward* the 12-month ideal more directly than the cloud approach did — the deployed Docker image is literally the on-prem story.

### 0C-bis Implementation Alternatives (decision: B′ by user at premise gate)
```
APPROACH A: Vision-LLM extraction + deterministic rules  (original recommendation)
  Effort: M | Risk: Low-Med | Rejected at premise gate: cloud dependency contradicts
  the firewall requirement; verbatim-transcription autocorrect risk on the warning.

APPROACH B′: Local OCR (PaddleOCR) + preprocessing + targeted verification  (CHOSEN — user)
  Summary: OpenCV preprocess → PP-OCRv4 words+boxes+confidences → fuzzy targeted search
  of expected values → deterministic rules; evidence crops from bounding boxes.
  Effort: M | Risk: Med (OCR fidelity on decorative fonts — gated at M0)
  Pros: verbatim by construction (title-case trap caught naturally); real confidences;
        bounding-box provenance; firewall-native; deterministic 5s; no API keys
  Cons: weaker than VLMs on very bad photos (mitigated: preprocessing + honest NEEDS
        REVIEW); field localization is our code, not a model's
  Reuses: PaddleOCR, OpenCV, off-the-shelf fuzzy matching

APPROACH C: B′ + queue infrastructure  (ideal-architecture variant)
  Rejected: queue infra is over-scope for the prototype; bounded concurrency suffices.
```

### 0E Temporal Interrogation (decisions resolved now)
- **Hour 1:** monorepo: `api/` (FastAPI + PaddleOCR + OpenCV), `web/` (Next.js), one Dockerfile; rules engine schema `{field: {status, label_value, app_value, crop, reason?}}`; engine choice parameterized for M0.
- **Hour 2-3:** canonical 27 CFR 16.21 text embedded as constant (both required sentences); normalization spec (NFC, collapse whitespace, unify quotes, case-fold only where a rule allows); ABV grammar incl. "ALC. 45% BY VOL."; warning anchor = fuzzy locate of `GOVERNMENT WARNING` allowing OCR confusables (0/O, 1/I).
- **Hour 4-5:** OCR confidence threshold default (word conf < 0.6 → field NEEDS REVIEW — tuned at M0); batch concurrency 4; 8MB cap client+server; container memory sizing for PaddleOCR.
- **Hour 6+:** golden set ~10 labels incl. adversarial traps; keyboard-complete flow, WCAG AA; README leads with the architecture argument (deterministic rules + local inference) and the firewall/on-prem story.

## CEO Review — 11 Sections (auto-decided per /autoplan principles)

### Section 1: Architecture
```
  BROWSER (Next.js UI)
     │ multipart POST /api/verify (image + application fields)
     ▼
  FASTAPI ROUTE ──▶ VALIDATE (type/size/pixels) ──▶ PREPROCESS (OpenCV:
     │                    │ reject→4xx                deskew/contrast/glare)
     │                    ▼                                │
     │              [worker process pool, N=cores]         ▼
     │                    └──────────▶ OCR (PaddleOCR: words+boxes+conf)
     │                                     │
     ▼                                     ▼
  RESPONSE ◀── RULES ENGINE (pure fn) ◀── LOCATOR (targeted fuzzy search
  {fields[], overall, timings}             of expected values + warning anchor)
```
- Happy/nil/empty/error paths per flow traced in Section 4 diagram.
- **Finding A1 (auto-approved, P1)**: PaddleOCR is not safely concurrent in one process — the plan now specifies a process worker pool (N = CPU cores) with a bounded queue; queue-full → 429 "busy".
- Scaling: CPU-bound; 10x load saturates the pool → queue wait grows visibly (elapsed-time indicator), 100x needs horizontal replicas — out of prototype scope, noted in README.
- SPOF: single container, acceptable and stated. Rollback: redeploy previous image tag — stateless, trivial.
- Security architecture: one public endpoint, no auth (demo), rate-limited; no secrets exist in the system at all (local inference) — the strongest possible posture for a public demo.
- Production failure scenario: OCR worker OOM on a pathological image → pool respawns worker, request fails to NEEDS REVIEW (`system error`) with retry; batch unaffected.

### Section 2: Error & Rescue Map
```
  CODEPATH                 | WHAT CAN GO WRONG            | EXCEPTION/SIGNAL      | RESCUED? | ACTION                       | USER SEES
  -------------------------|------------------------------|-----------------------|----------|------------------------------|--------------------------
  POST /api/verify         | wrong file type              | ValidationError       | Y        | 400                          | "PNG or JPG only"
                           | file >8MB / >40MP pixels     | PayloadTooLarge       | Y        | 413                          | "Image too large — max 8MB"
                           | corrupt/undecodable image    | ImageDecodeError      | Y        | 422                          | "Couldn't read this image"
                           | rate limit exceeded          | RateLimited           | Y        | 429 + Retry-After            | "Busy — try again in a moment"
  preprocess/ocr           | OCR timeout (>10s)           | OCRTimeoutError       | Y        | kill worker task             | NEEDS REVIEW (system error) + Retry
                           | worker crash / OOM           | WorkerDied            | Y        | respawn pool worker          | NEEDS REVIEW (system error) + Retry
                           | model file missing at boot   | StartupError          | Y        | fail /healthz, no traffic    | deploy fails loudly, not silently
  locator                  | warning anchor not found     | (not exceptional)     | Y        | field verdict                | NEEDS REVIEW (absent from label)
                           | no ABV/net-contents pattern  | (not exceptional)     | Y        | field verdict                | SUPERSEDED (Rev 2.1): commodity-aware — NOT REQUIRED / not-visible / coverage-gated finding
                           | low word confidence (<0.6)   | (not exceptional)     | Y        | field verdict                | NEEDS REVIEW (unreadable) + crop
  batch client             | one item fails               | per-item error        | Y        | row error, rest continue     | red row + per-row Retry
                           | navigate away mid-batch      | beforeunload          | Y        | warn dialog                  | "Batch in progress — leave?"
```
No catch-all handlers: the route boundary maps the named taxonomy above; anything unmapped is a 500 logged with request id + stage — visible, never swallowed. **0 GAPS** after A1.

### Section 3: Security & Threat Model
- **Finding S1 (auto-approved, P1)**: image parser attack surface (decompression bombs, malformed containers) — added pixel-count cap (40MP) + Pillow safe-decode before OpenCV, size caps client and server side. Likelihood M / Impact M → mitigated.
- **Finding S2 (auto-approved, P1)**: CSV export formula injection (`=HYPERLINK(...)` in a brand name becomes executable in Excel) — all exported cells prefixed per OWASP CSV rules. Likelihood L / Impact M → mitigated.
- **Finding S3 (auto-approved, P2)**: batch manifest filenames — sanitize/never use as paths; map by exact uploaded-name string only. Likelihood L / Impact H → mitigated.
- DoS: rate limit + bounded queue + 429; no API key to steal; no PII stored; no injection surfaces (no DB, no shell, no LLM prompts — prompt injection is structurally absent in the local architecture).
- Dependency risk: paddle/paddleocr pinned; image built from pinned base; models baked at build (no runtime downloads).

### Section 4: Data Flow & Interaction Edge Cases
```
  IMAGE ──▶ VALIDATE ──▶ PREPROCESS ──▶ OCR ──▶ LOCATE ──▶ COMPARE ──▶ RENDER
    │           │             │           │        │           │          │
  [nil? →     [wrong type   [cv2 error  [timeout [anchor     [no app    [row renders
   400]        →400]         →NEEDS      →NEEDS   missing     value →    crop lazily;
  [empty file [>8MB/40MP     REVIEW]     REVIEW]  →absent]    NOT        broken crop →
   →422]       →413]                              [conf<0.6   CHECKED]   text fallback]
                                                  →unreadable]
```
| Interaction | Edge case | Handled? | How |
|---|---|---|---|
| Verify click | double-click | Y (**auto-approved F4a**) | button disabled while in-flight |
| Verify click | all form fields empty | Y (**F4b**) | inline prompt "enter at least one field to check" |
| Batch | 500+ files dropped | Y (**F4c**) | batch capped at 500 with message; results table virtualized |
| Batch | duplicate filenames | Y | suffixed display names; manifest matches exact name, ambiguity → row NEEDS REVIEW (system) |
| Batch | browser closed mid-run | Y | beforeunload warning; completed rows already rendered (no server state to leak) |
| Results | slow connection | Y | rows stream; skeleton rows for pending |
| Form | unicode/emoji in fields | Y | NFC normalize; comparison spec already unicode-aware |

### Section 5: Code Quality (greenfield conventions set now)
- Rules engine and parsers: pure functions, table-driven cases; one shared `normalize.ts`-equivalent module (single source for the spec in 0E) — prevents the classic drift where the warning comparator and brand comparator normalize differently.
- Per-field locator = small strategy objects with a common interface; heuristics stay quarantined per field instead of one 300-line function (cyclomatic guard).
- Error taxonomy in one module; route boundary is the only place exceptions map to HTTP.
- No over-engineering flags: no queue infra, no DB, no state machines beyond per-item status enum.

### Section 6: Test Review
```
  NEW UX FLOWS: single verify; sample demo; batch upload+manifest; per-row retry; CSV export
  NEW DATA FLOWS: image→OCR→locate→compare→render; manifest→record mapping
  NEW CODEPATHS: parsers (ABV, proof, net contents), normalizers, warning anchor+diff,
                 caps check, bold heuristic, confidence gate, overall-status fold
  NEW ASYNC: worker pool dispatch, batch concurrency, per-item timeout
  NEW INTEGRATIONS: none external (by design)
  NEW ERROR PATHS: all rows of Section 2 table
```
- Unit (pytest): every parser/normalizer/comparator branch incl. boundary (tolerance-band edges per commodity e.g. 40.3 vs 40.31 spirits, class-boundary overrides 14/21/24% and 2.5%/0.5%, range labels, "0.75 L vs 750 mL", quote unification, NFC); warning diff token cases; caps check on title-case trap; overall-status fold incl. NOT CHECKED exclusion.
- Golden-set eval (M0 harness, pinned OCR version, snapshot expectations): 2am-Friday test = title-case trap yields caps-line MISMATCH; hostile-QA set = cat photo, 0-byte file, PDF renamed .png, 20MB image, script-font brand.
- Integration: API route happy + every 4xx/timeout path. E2E smoke (Playwright): sample button → verdicts render <5s.
- Chaos: kill an OCR worker mid-batch → affected row NEEDS REVIEW(system), batch completes.
- Flakiness guard: OCR output pinned by engine version; eval failures on version bump are signal, not flake. **Diagram gaps: 0** after the above specs were added to milestone definitions.

### Section 7: Performance
- **Finding P1a (auto-approved, P1)**: model load must happen at container boot with a warmup inference, else the first evaluator request eats a ~5-10s cold model init — the exact first-impression failure Sarah described. `/healthz` returns ready only post-warmup.
- **Finding P1b (auto-approved, P2)**: free-tier host cold starts (Render/Fly sleep) would present a dead-feeling demo — plan notes a paid/always-on instance or keep-alive for the evaluation window, and README states it.
- Worker pool size = cores; batch concurrency aligned to pool size (no point posting 4 concurrent if pool is 2). Memory: ~2GB container (PaddleOCR models + OpenCV buffers + headroom); 40MP pixel cap bounds decode memory.
- p99 path: huge-but-legal image + dense text → preprocess+OCR ~4s; within budget; measured at M0.

### Section 8: Observability
- Structured stdout logs: request id, stage timings (validate/preprocess/ocr/locate/compare), verdict summary per request — a 3-weeks-later bug is reconstructable from one log line.
- `/healthz` (post-warmup readiness) + `/metrics-lite` (in-memory counters: requests, p50/p95, verdict distribution, error rates) — verdict-distribution drift is the canary for OCR regressions.
- Runbook table in README: symptom → likely stage → fix (e.g., "everything NEEDS REVIEW(unreadable) → check image pipeline / threshold config").

### Section 9: Deployment & Rollout
- One Docker image, models baked at build; no migrations, no flags needed; rollout = deploy, rollback = previous tag (minutes).
- Post-deploy verification: /healthz ready → scripted sample-label verify (the demo sample doubles as the smoke test) → check p50 in logs. Deploy-time risk window: none (stateless, single service).
- Environment parity: identical image local/deployed — and parity *is the product story* (same image runs inside TTB's firewall).

### Section 10: Long-Term Trajectory
- Reversibility: 4/5 (Extractor interface isolates the engine; rules engine pure).
- Debt introduced: locator heuristics will accrue special cases — contained by per-field strategy objects + golden set regression harness. Documentation debt low (README is a deliverable).
- 1-year question: a new engineer reads pipeline stages left-to-right and the rules as data tables — obvious. Platform potential: rules engine is the CFR-engine substrate (TODOS P3).

### Section 11: Design & UX (CEO-level; deep pass in Phase 2)
```
  [Empty state]──upload/sample──▶[Form + image preview]──Verify──▶[Verifying: staged
      │ big drop zone + "Try a sample"                              progress + elapsed]
      ▼                                                                  │
  [Batch table view]◀──multi-drop                                        ▼
      rows stream in                                    [Results: overall banner first,
      filter/export                                      then per-field rows w/ crops]
```
- IA: 1) overall banner, 2) per-field verdict rows (worst first), 3) evidence crops, 4) export. State coverage: LOADING (staged), EMPTY (drop zone + sample), ERROR (taxonomy messages), SUCCESS, PARTIAL (batch streaming) — all specified.
- AI-slop risk: flagged — one-task layout, no dashboard chrome; Phase 2 owns the full pass.
- Accessibility is M4 scope with WCAG AA contrast + keyboard-complete flow + status = color+icon+word.

## Required Outputs (CEO phase)

### NOT in scope
- Full CFR rules engine w/ citations (TODOS P3) · COLA integration (Marcus: years away) · multi-image front/back (TODOS P2, assumption documented) · retry-with-escalation (TODOS P3) · application-PDF ingestion (TODOS P2) · optional on-prem VLM assist (TODOS P3) · cloud ML anything (user decision) · beverage-type checklist — REVERSED at Rev 2.1 gate: core commodity awareness now M2 scope (deeper type rules remain deferred).

### What already exists
Greenfield repo (README only). Leverage map: PaddleOCR/OpenCV (Layer-1 OCR + preprocessing), rapidfuzz (fuzzy matching), embedded 27 CFR 16.21 text (statutory constant), FastAPI/Next.js (commodity scaffolding). Nothing is being rebuilt that a maintained library provides.

### Dream state delta
Written in Step 0C — the local pivot moves the prototype *closer* to the 12-month on-prem ideal than the original cloud plan.

### Failure Modes Registry
```
  CODEPATH        | FAILURE MODE              | RESCUED? | TEST? | USER SEES?              | LOGGED?
  ----------------|---------------------------|----------|-------|-------------------------|--------
  upload/validate | bad type/size/corrupt     | Y        | Y     | plain-language 4xx      | Y
  ocr worker      | timeout/crash/OOM         | Y        | Y     | NEEDS REVIEW + Retry    | Y
  locator         | anchor/pattern not found  | Y        | Y     | NEEDS REVIEW (absent)   | Y
  confidence gate | unreadable field          | Y        | Y     | NEEDS REVIEW + crop     | Y
  batch item      | single-item failure       | Y        | Y     | red row + Retry         | Y
  boot            | model missing/corrupt     | Y        | Y     | deploy fails (healthz)  | Y
  export          | formula injection         | Y        | Y     | escaped cell            | n/a
```
**CRITICAL GAPS: 0** (every row rescued, tested, visible, logged).

## Decision Audit Trail (Phase 1)

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | Skip /office-hours prerequisite | Mechanical | P6 | README already contains full discovery material | office-hours run |
| 2 | CEO | Mode = SELECTIVE EXPANSION | Mechanical | autoplan override | mandated | — |
| 3 | CEO | Approach A (vision-LLM) recommended at 0C-bis | Taste → superseded | P1 | best coverage of bad-photo requirement | — |
| 3a | CEO | **USER at premise gate: reverse P3 → local/OCR (B′)** | User decision | — | firewall-native; codex voice concurred independently | Approach A |
| 4 | CEO | Accept expansions 1-4 (evidence, diff, cross-check, demo) | Mechanical | P2 | in blast radius, <1d CC, no new infra | — |
| 5 | CEO | Beverage-type checklist → provisional defer | Taste (gate) | P2 borderline | 3-5 files, borderline radius | — |
| 6 | CEO | Defer CFR engine, multi-image, retry-escalation, app-ingestion | Mechanical | P3 | outside blast radius / new scope | build now |
| 7 | CEO | Keep batch mode vs codex "cut it" | Taste (gate) | P1 | explicit stakeholder requirement (Sarah) | codex #1 |
| 8 | CEO | Screening-assistant framing, no approval verdicts | Mechanical | P5 | codex #14; honest authority boundary | "never false PASS" claim |
| 9 | CEO | LIKELY MATCH as explicit state | Taste (gate) | P5 | codex #15; surfacing policy calls | silent MATCH-with-note |
| 10 | CEO | M0 feasibility spike added | Mechanical | P1 | codex #25 + Claude 2.1: gate riskiest premise first | build UI first |
| 11 | CEO | Reject triage-only reframe (codex #24) | Mechanical | P6 | README lists required fields; user premise P1 confirmed | narrow-checks-only product |
| 12 | CEO | Worker pool, pixel caps, CSV escaping, batch cap, warmup, cold-start note, in-flight disable | Mechanical | P1 | Sections 1-9 findings, all small & in radius | defer to implementation |
| 13 | CEO | Visual evidence crops INTO scope (was deferred) | Mechanical | P1 | OCR pivot makes bboxes reliable; both voices called it highest-trust feature | keep deferred |

## Design Review — Phase 2 Record (dual voices + 7 passes)

### Litmus Scorecard (cross-model)
```
  Check                                    Claude   Codex   Consensus
  ─────────────────────────────────────── ──────── ─────── ──────────────────────
  1. Brand unmistakable in first screen?   FAIL     NO      CONFIRMED FAIL → identity line added
  2. One strong visual anchor?             unspec   YES     RESOLVED → banner anchors verdict, image anchors evidence
  3. Scannable by headlines only?          partial  NO      CONFIRMED → three named regions added
  4. Each section has one job?             partial  NO      CONFIRMED → master-detail structure added
  5. Cards actually necessary?             PASS     NO      CONFIRMED → rows/table; cards only summary + warning group
  6. Motion improves hierarchy?            unspec   NO      CONFIRMED → in-place updates, reduced-motion, no decoration
  7. Premium without shadows?              can't    YES     RESOLVED → UI constants carry it; shadow hierarchy banned
  Hard rejections triggered:               0 as planned; 10 pre-emptive guardrails written into the spec
```

### Pass ratings (before → after fixes)
| Pass | Before | After | What closed the gap |
|---|---|---|---|
| 1 Info architecture | 6 | 9 | Master-detail, three regions, fixed checklist order, headings |
| 2 Interaction states | 7 | 9 | Banner copy per state, empty-state matrix, item-state names, partial-preservation rule |
| 3 User journey | 4 | 8 | Daily loop, keystroke budget, evaluator sample narrative, batch completion payoff |
| 4 AI-slop risk | 3 | 8 | Hard-rejection guardrails, real typeface, no dashboard cosplay, no chip wallpaper |
| 5 Design system | 2 | 7 | UI constants block (tokens-in-plan); no DESIGN.md — /design-consultation recommended post-review |
| 6 Responsive + a11y | 4 | 9 | WCAG 2.2 AA as M1 acceptance criteria, master-detail responsive rules, focus/live-region spec |
| 7 Unresolved decisions | — | — | All resolved except DESIGN.md creation (deferred, TODOS) |

Overall design score: 4/10 → 8/10.

### Design decisions changing other phases (feeds eng review)
- "Absent" split: readable+not-found → MISMATCH(absent); unreadable → NEEDS REVIEW — a rules-engine change.
- Two-axis overall status (screening result × attention state); partial results preserved on timeout.
- Stale-result + explicit Re-check on post-result edits — API/state contract addition.

### Decision Audit Trail (Phase 2 additions)
| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 14 | Design | Master-detail batch layout (reject inline row expansion) | Mechanical | P5 | Both voices: 300 expanded rows unusable; codex structural answer adopted |
| 15 | Design | 5 data states → 3 visual families; compact lozenges | Mechanical | P5 | Both voices: taxonomy overload / chip wallpaper |
| 16 | Design | Accessibility moved to M1 acceptance criteria | Mechanical | P1 | Both voices: retrofit ships keyboard traps |
| 17 | Design | Fixed checklist row order, never severity-sorted | Mechanical | P5 | Spatial memory for 100-label/day agents |
| 18 | Design | Absent-field disposition split (MISMATCH vs NEEDS REVIEW) | Mechanical | P1 | Codex: confident not-found is substantive |
| 19 | Design | Warning as grouped check w/ disclosure + labeled diff language | Mechanical | P5 | Both voices converged |
| 20 | Design | Evaluator sample narrative (5 named proof points) | Mechanical | P2 | Codex; small scope, evaluation-critical |
| 21 | Design | Anchor synthesis (banner=verdict anchor, image=evidence anchor) | Taste (minor, resolved) | P5 | Voices differed; both preserved |
| 22 | Design | No DESIGN.md — UI constants in plan; /design-consultation deferred | Taste (gate) | P3 | Full design system out of take-home scope |

## DX Review — Phase 3.5 Record

### DX Dual Voices — Consensus Table
```
  Dimension                        Claude   Codex   Consensus
  ─────────────────────────────── ──────── ─────── ──────────────────────────────
  1. Getting started < 5 min?     6/10 NO  4/10 NO CONFIRMED FAIL → prebuilt GHCR image
  2. API naming guessable?        6/10     4/10    CONFIRMED gap → contract + envelope pinned
  3. Error messages actionable?   7/10     2/10*   CONFIRMED gap (*runtime excellent, setup absent) → startup table
  4. Docs findable & complete?    7/10     5/10    CONFIRMED gap → README to M1, skim order defined
  5. Upgrade path safe?           7/10     4/10    CONFIRMED gap → locks, checksums, make targets, no-egress CI test
  6. Dev environment friction?    5/10     3/10    CONFIRMED gap → no-Docker path + frontend dev loop documented
```
Both voices found the same shape: deployed-URL path is top-decile (<1 min TTHW); the clone path was the risk. TTHW: ~12-25 min → target <5 min interaction (pull-based). DX score: initial ≈4.6/10 → 8/10 after spec.

### Decision Audit Trail (Phases 3 + 3.5 additions)
| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 23 | Eng | Static export served by FastAPI (drop Node runtime) | Mechanical | P5 | Both voices; one process, one port |
| 24 | Eng | In-process job API for batch (submit/status/result/cancel) | Mechanical | P1 | Codex 16-18 + Claude A5; makes cancel truthful |
| 25 | Eng | Evidence as coordinates; client-side crops | Mechanical | P5 | Codex 5; kills base64 bloat |
| 26 | Eng | Absence requires coverage model; "not found in submitted image" wording | Mechanical | P1 | Codex 9-10; confidence ≠ coverage |
| 27 | Eng | Warning three-outcome model; "verbatim by construction" phrasing retracted | Mechanical | P1 | Codex 11; honesty about probabilistic input |
| 28 | Eng | Bold M0 kill-gate (ship "confirm visually" if precision poor) | Mechanical | P5 | Codex 15 + Claude H2 |
| 29 | Eng | Fly.io named as the platform (drop "or Render") | Mechanical | P3 | Codex 21; placeholders block measurement |
| 30 | Eng | Per-field length-calibrated thresholds + ambiguity margin | Mechanical | P1 | Codex 8 + Claude T1 |
| 31 | DX | Prebuilt GHCR image as default compose path | Mechanical | P1 | Both voices; highest-leverage DX fix |
| 32 | DX | README skeleton = M1 exit criterion | Mechanical | P1 | Both voices; graded artifact can't be last |
| 33 | DX | API contract + response envelope pinned pre-M1 | Mechanical | P5 | Both voices; plan carried two schemas |
| 34 | DX | make test/eval/smoke/lint named commands + no-egress CI test | Mechanical | P1 | Both voices; repro made invocable |

## Implementation Tasks (aggregated across phases)
Synthesized from all four review phases. P1 blocks ship; P2 lands same branch; P3 follow-up.

- [ ] **T4/ceo-review (P1, human: ~1h / CC: ~10min) — api** — Bake OCR models into image at build; warmup inference at boot; /healthz ready-after-warmup
- [ ] **T3/ceo-review (P1, human: ~1h / CC: ~10min) — api** — Upload hardening: type/size/40MP pixel caps, safe decode, error taxonomy at route boundary
- [ ] **T1/ceo-review (P1, human: ~2h / CC: ~15min) — api** — Run M0 OCR feasibility spike (PaddleOCR vs tesseract.js on 8-label golden set, report fidelity + latency)
- [ ] **T2/ceo-review (P1, human: ~2h / CC: ~15min) — api** — Process worker pool for OCR (N=cores, bounded queue, 429 on full, respawn on crash)
- [ ] **T3/design-review (P1, human: ~1h / CC: ~10min) — api** — Two-axis overall status + absent-field disposition split (MISMATCH vs NEEDS REVIEW) + partial-result preservation
- [ ] **T1/design-review (P1, human: ~4h / CC: ~30min) — web** — Build master-detail layout (Start-a-check / Applications list / Selected label) with fixed-order result rows and stable streaming
- [ ] **T4/design-review (P1, human: ~2h / CC: ~20min) — web** — Keyboard-complete flow as M1 acceptance: native controls, focus order stable during streaming, focus-to-error, live regions, crop-zoom dialog
- [ ] **T2/design-review (P1, human: ~2h / CC: ~20min) — web** — Implement all banner/state copy strings and 3-visual-family verdict lozenges with next-action language
- [ ] **T7/eng-review (P1, human: ~1h / CC: ~10min) — api** — EXIF transpose + angle classifier + HEIC/WebP decode; static export served by FastAPI
- [ ] **T2/eng-review (P1, human: ~4h / CC: ~30min) — api** — M0 on target hardware: latency/memory/warmup on exact Fly VM class; warning exact-match rate gate; raw-vs-preprocessed; bold precision kill-gate; FP/FN curves on ~25-image calibration set
- [ ] **T4/eng-review (P1, human: ~4h / CC: ~30min) — api** — In-process job API (submit/status/result/cancel) with two-priority scheduling and Retry-After
- [ ] **T1/eng-review (P1, human: ~1d / CC: ~1h) — api** — Build locator as named component: line clustering, reading order, cross-line join, per-field calibrated thresholds + ambiguity margin, synthetic-layout test corpus
- [ ] **T3/eng-review (P1, human: ~4h / CC: ~30min) — api** — Worker supervision: shared measured pool, queue-vs-exec timeouts, terminate-and-replace, recycle policy, thread pinning, warmed-spare shed-load
- [ ] **T5/eng-review (P1, human: ~2h / CC: ~15min) — api** — Warning three-outcome model + char-level confusable handling + statutory constant provenance/checksum; coverage gate before absent→MISMATCH
- [ ] **T6/eng-review (P1, human: ~2h / CC: ~15min) — web** — Evidence as coordinates: client-side crop rendering from retained file, object-URL cleanup, bounded responses
- [ ] **T3/devex-review (P1, human: ~1h / CC: ~10min) — api** — Pin /api/verify contract: multipart image + application JSON, versioned envelope, reason codes, status enum; keep /docs reachable; curl example in CI
- [ ] **T2/devex-review (P1, human: ~2h / CC: ~15min) — docs** — README skeleton at M1: setup, run, curl, 6-line architecture, samples, troubleshooting table (exit 137, port, Docker), memory floor
- [ ] **T1/devex-review (P1, human: ~2h / CC: ~20min) — infra** — CI builds + publishes GHCR image; compose pulls prebuilt by default; make smoke as clean-machine proof
- [ ] **T8/ceo-review (P2, human: ~1h / CC: ~10min) — api** — Structured stage-timing logs + /metrics-lite counters (p50/p95, verdict distribution)
- [ ] **T7/ceo-review (P2, human: ~30min / CC: ~5min) — infra** — Always-on instance (or keep-alive) for evaluation window; document in README
- [ ] **T5/ceo-review (P2, human: ~1h / CC: ~10min) — web** — CSV export formula-injection escaping; batch cap 500 + virtualized results table
- [ ] **T6/ceo-review (P2, human: ~30min / CC: ~5min) — web** — In-flight verify button disable; empty-form inline prompt; beforeunload batch warning
- [ ] **T6/design-review (P2, human: ~1h / CC: ~10min) — web** — Evaluator sample chooser: five named proof-point examples incl. small batch
- [ ] **T5/design-review (P2, human: ~2h / CC: ~15min) — web** — Warning grouped check UI: summary + three subchecks + disclosure diff with labeled language
- [ ] **T7/design-review (P2, human: ~1h / CC: ~10min) — web** — UI constants tokens (18px base, 48px inputs, 44px targets, Public Sans, verdict colors AA/deuteranopia)
- [ ] **T8/eng-review (P2, human: ~2h / CC: ~15min) — api** — Security invariants: element-only rendering of OCR text, forwarded-header-only rate limit + global ceiling, lifecycle limits, log redaction (no raw values/OCR text)
- [ ] **T9/eng-review (P2, human: ~2h / CC: ~15min) — api** — Test suites: fuzzy boundary table, multi-line reassembly, load 3×pool, CSV manifest matrix, ABV confusables/proof-only
- [ ] **T10/eng-review (P2, human: ~2h / CC: ~15min) — web** — Batch client state machine reducer + interaction tests (edit-during-check, retry-after-cancel, undo-after-partial)
- [ ] **T5/devex-review (P2, human: ~1h / CC: ~10min) — docs** — No-Docker contributor path + frontend dev loop (uvicorn + next dev proxy); OCR_WORKERS/APP_PORT env vars documented
- [ ] **T4/devex-review (P2, human: ~2h / CC: ~15min) — infra** — make test/eval/lint targets; vendored models by checksum; locked deps; base image by digest; no-egress CI test; golden set committed with provenance
- [ ] **T8/design-review (P3, human: ~1h / CC: ~10min) — web** — Print-friendly single-label report view

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | ISSUES_OPEN (via /autoplan) | 8 proposals, 5 accepted, 4 deferred; premise gate reversed P3 → local/OCR |
| Codex Review | `/codex review` | Independent 2nd opinion | 4 | RAN (via /autoplan voices) | CEO 25 / Design struct. / Eng 23 / DX 10-point — all folded or logged |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN via /autoplan) | 43 issues, 0 critical gaps, all folded into plan |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | ISSUES_OPEN (via /autoplan) | score: 4/10 → 8/10, 9 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | ISSUES_OPEN (via /autoplan) | score: 5/10 → 8/10, TTHW: 12-25min → <5min |

**CROSS-MODEL:** Claude and Codex voices ran in all four phases. Eng and DX phases reached full consensus (6/6 each). CEO phase: 2 disagreements (batch scope, triage reframe) resolved with rationale. Design phase: structural recommendations merged (master-detail from Codex, checklist-order/journey from Claude). The user's premise-gate pivot to local OCR was independently supported by the Codex CEO voice.

**VERDICT:** ENG CLEARED — CEO/Design/DX open items are the gate decisions below; ready to implement once the final approval gate resolves.

**APPROVED at final gate (2026-07-31):** user accepted all recommendations — batch mode kept, LIKELY MATCH explicit, UI constants stand in for a design system. **Rev 2.1 RATIFIED at gate (2026-07-31): research integration approved — commodity awareness into M2 (reversing the earlier deferral), ABV three-band model, NOT REQUIRED disposition, weight-contrast bold model.**

NO UNRESOLVED DECISIONS
