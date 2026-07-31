# Codex Eng Voice (architecture challenge) — 2026-07-31

The plan is much less settled than its “CRITICAL GAPS: 0” claim suggests. The biggest unresolved risk is not raw OCR accuracy; it is whether the system can distinguish “the label is wrong” from “OCR or localization was wrong.” Several current rules can confidently produce false mismatches—or even false matches.

## Architectural blockers

1. **The process and memory model is internally inconsistent.**

“Worker pool = CPU cores” assumes each PaddleOCR worker can hold its own model. A four-worker pool may mean four model copies, plus OpenCV image buffers, Python, FastAPI, and Next.js. That is unlikely to fit the stated ~2 GB container.

It gets worse if the ASGI server starts multiple web workers: each web process may create its own OCR pool, multiplying memory and CPU oversubscription. The plan needs one explicit topology:

- one API process;
- one shared OCR pool of a measured size;
- exact per-worker resident memory;
- host CPU quota awareness rather than `os.cpu_count()`;
- no accidental pool creation during Next.js build, reload, or worker import.

Concurrency must be selected from measured memory and CPU, not number of cores.

2. **“Kill worker task after 10s” is not a straightforward process-pool operation.**

Common Python process pools cannot reliably terminate only the timed-out job. Canceling the future generally does not stop native Paddle inference. Killing a worker can also break or poison the pool, lose another queued task, and leave native child processes or shared memory behind.

The plan needs a concrete supervision design: dedicated long-lived worker processes with task IDs, hard termination and replacement semantics, startup/warmup state, crash-loop limits, and a distinction between queue timeout and execution timeout.

3. **One Docker image does not yet define how two servers run safely.**

Next.js and FastAPI need a supervisor, signal propagation, readiness behavior, port routing, and graceful shutdown. If either child dies, the container should fail rather than continue half-alive. `/healthz` must cover both the frontend and a functioning OCR worker, not merely model initialization.

Also specify whether Next.js proxies uploads to FastAPI. Proxying duplicates bandwidth and memory and introduces independent request-size and timeout limits. Direct browser-to-FastAPI requests introduce same-origin/CORS and deployment-routing concerns.

4. **The “stateless” design clashes with long-running batch work.**

A 300-item batch is hundreds of independent HTTP requests whose results exist only in browser memory. Refresh, tab crash, laptop sleep, transient network loss, or deployment destroys batch continuity. `beforeunload` does not solve those cases and is unreliable on mobile.

This may be acceptable for a take-home, but it must be presented as a severe prototype limitation. “Partial-result preservation” currently means only “while this tab remains healthy.”

5. **Evidence delivery can overwhelm the browser.**

Returning full images plus crops as base64 inside JSON for hundreds of records creates roughly 33% encoding overhead, large React state, repeated image data, long garbage-collection pauses, and potentially hundreds of decoded bitmaps. Table virtualization does not fix retained memory.

Define:

- whether the browser retains the original local file and renders boxes client-side;
- whether the API returns coordinates instead of crop bytes;
- thumbnail generation limits;
- object URL cleanup;
- maximum total batch bytes, not just per-file size.

A batch cap of 500 × 8 MB still permits a multi-gigabyte browser session.

## Targeted search is underspecified

The phrase “fuzzy-search across OCR tokens” hides most of the system’s actual complexity.

6. **Token reassembly has no defined algorithm.**

Paddle output is not a trustworthy prose stream. Labels have columns, curved baselines, rotated text, seals, overlapping typography, and front/back-style panels in one photograph. Sorting by top-left coordinates will interleave unrelated blocks.

The plan must define candidate construction:

- line clustering from quadrilaterals;
- permitted horizontal and vertical gaps;
- orientation handling;
- hyphenation across lines;
- whether candidates may cross line or region boundaries;
- maximum token span;
- reading direction;
- punctuation attached as separate tokens;
- duplicated and overlapping detections;
- rotated or curved sequences.

Without geometric constraints, expected words can be assembled from unrelated locations.

7. **Searching for an expected value anywhere can produce false matches.**

A brand or class/type may appear in marketing copy, an importer statement, a product story, or another label depicted in artwork. “750 mL” may appear in a comparison or multipack statement. ABV values can coexist with proof, serving facts, or multiple product variants.

The system needs field-specific candidate ranking and ambiguity handling. If two plausible candidates exist, it should not silently select the closest. Candidate provenance should include the complete source span and surrounding context.

8. **Thresholds cannot be global.**

A similarity threshold appropriate for a long class/type is dangerous for a three-character brand. Edit distance behaves differently across string lengths, scripts, punctuation, and OCR confusables. A short expected value can fuzzy-match by accident; a long expected value can score well despite a legally meaningful missing word.

Thresholds need calibration by field and length, plus an ambiguity margin between first and second candidates. The test plan should measure false-positive and false-negative curves, not merely “read fidelity.”

9. **OCR confidence does not establish absence.**

High confidence on the words OCR did detect says nothing about text it failed to detect. Therefore “readable label + no expected hit = MISMATCH” cannot be inferred from token confidence alone. The omitted field might be in glare, missed by detection, extremely small, or outside the photograph while every detected word has confidence 0.99.

The plan needs an image- or region-level coverage/readability model. If it cannot establish that the relevant label region was adequately observed, not-found must remain uncertain. Otherwise the absent-field split is conceptually unsound.

10. **The single-image limitation makes absence judgments especially unsafe.**

Alcohol labels commonly distribute information across panels. A photograph of only the front cannot support “government warning absent” or “net contents absent” conclusions about the full label. Documenting the limitation does not prevent systematic false mismatches.

At minimum, the UI must ask the user to attest that all relevant panels are visible. More honestly, absence-sensitive checks should require multi-image input or be explicitly labeled “not visible in the submitted image,” not “label mismatch.”

## Government-warning verification is not exact

11. **OCR output is not “verbatim by construction.”**

OCR is a probabilistic transcription. A legally correct label can be reported as incorrect because OCR changed one glyph; an incorrect label can be reported as correct through the inverse error. Word confidence is not calibrated evidence that every character is exact.

An exact string comparison is deterministic, but the input to it is not exact. Calling the overall check “exact-match” overstates what is proven.

The warning should have at least three outcomes:

- verified textual match only when every relevant glyph has sufficiently strong evidence;
- definite mismatch only when the image evidence supports the differing glyphs;
- unable to verify when OCR uncertainty or segmentation could explain the difference.

A low-confidence gate applied only to whole words is inadequate for punctuation, plural endings, capitalization, and characters such as `I/l/1` or `O/0`.

12. **Fuzzy anchoring can invalidate an exact downstream comparison.**

If the warning anchor is partially misread, how is the warning block delimited? A fixed number of subsequent tokens can absorb unrelated text or omit a wrapped line. Multi-column labels can splice text from adjacent regions. The plan needs geometric block segmentation and rules for paragraph boundaries, punctuation, parenthetical markers, and line breaks before any statutory comparison is meaningful.

13. **Anchor handling contradicts the absence policy.**

The error table says “warning anchor not found → NEEDS REVIEW (absent from label),” while the design says confidently not found should be MISMATCH. This is not merely copy inconsistency; it changes overall status. Government warning is mandatory and always checked, so the rules must state separately:

- complete label visible and readable, warning not found;
- relevant panel missing;
- warning region present but unreadable;
- anchor mistranscribed;
- anchor found but statutory body incomplete.

14. **The statutory constant requires provenance and version control.**

“Both required sentences” is not enough. Preserve the exact authoritative source, effective version, punctuation, paragraph markers, permitted formatting interpretation, and a test that the embedded constant has not been editorially altered. Unicode normalization can itself alter code points; the warning path must specify exactly which transformations are legally neutral.

## Bold detection is probably not viable as stated

15. **Stroke width is not a reliable bold classifier without a reference.**

Observed stroke width varies with font size, resolution, antialiasing, thresholding, glare, compression, perspective, and camera sharpening. A large regular font can have wider strokes than a small bold font. Adaptive thresholding can manufacture or erase apparent weight.

The plan does not identify what the prefix is compared against. An absolute threshold will not generalize; comparison with body text requires the same typeface, scale, and imaging conditions, which cannot be assumed.

For this prototype, “unknown/confirm visually” may be the only defensible automated result. M0 should explicitly determine whether the heuristic has useful precision, and the feature should be removed if it mostly produces unknowns or misleading yes/no results. Synthetic labels are especially unsuitable for validating this heuristic.

## Batch and latency problems

16. **Client concurrency and server capacity are separate controls.**

If each browser submits four jobs and ten users open the public demo, the server sees forty requests. A bounded server queue helps, but the UI needs retry/backoff semantics that respect `Retry-After`, avoid synchronized retry storms, and distinguish:

- uploading;
- waiting in the server queue;
- actively running OCR;
- timed out before execution;
- timed out during execution.

17. **The 10-second timeout conflicts with queueing.**

If the timer begins at request submission, a healthy job can fail solely because earlier jobs occupied the pool. If it begins after dequeue, the HTTP request may remain open far longer than ten seconds. Proxy and platform timeouts also operate independently.

A synchronous request model is questionable for a 300-item batch. Even without external queue infrastructure, an in-process job API with submit/status/result semantics may be necessary for cancellation, fair scheduling, and truthful progress.

18. **Batch cancellation does not actually cancel uploaded queued work.**

“Cancel waiting checks” on the client prevents future submissions, but any requests already accepted into the server queue remain alive unless the API supports task cancellation. The wording and implementation need to match.

19. **The five-second metric omits material time.**

The stated budget excludes or under-specifies:

- client decode and resize, especially on old laptops;
- multipart encoding and upload;
- Next.js proxying;
- server queue wait;
- response serialization and transfer;
- base64 crop payloads;
- browser image decode and React rendering;
- initial JavaScript download/hydration;
- CPU throttling and noisy-neighbor effects;
- container wake, restart, and post-deploy warmup;
- EXIF orientation correction;
- multiple preprocessing/OCR passes;
- dense-text detection cost.

A warm p50 can look excellent while most evaluator experiences are poor. Publish cold p50, warm p50/p95, queue-inclusive latency, and batch time-to-first-result/time-to-completion.

## Deployment risks

20. **The claimed resource envelope is unproven.**

A baked Paddle stack plus native libraries and models can produce a very large image, slow pulls, slow deploys, substantial boot time, and memory spikes during model loading. Platform health-check deadlines may expire before warmup completes.

M0 needs to measure:

- compressed image size;
- cold boot and warmup time;
- steady and peak RSS per OCR worker;
- RSS during 40 MP decode/preprocessing;
- inference under actual container CPU limits;
- simultaneous-worker throughput;
- behavior under memory pressure.

21. **CPU and native-library portability need explicit validation.**

Local success does not prove hosted success. Paddle/OpenCV builds can depend on architecture, instruction sets, system libraries, and threading runtimes. Native libraries may internally start multiple threads, so several worker processes can catastrophically oversubscribe a small VM.

Pin thread counts and test the exact production image on the exact target VM class. Fly and Render should not remain interchangeable placeholders because their CPU allocation, sleep behavior, memory limits, health checks, proxy limits, and architecture differ.

22. **Rate limiting by IP is fragile behind proxies.**

The service must trust forwarded IP headers only from the hosting proxy. Otherwise clients may spoof them, or every user may appear to share one proxy address. In-memory limits also reset on restart and diverge across replicas. That may be acceptable, but it should be described honestly.

23. **“No PII stored” is not established.**

Uploaded artwork and application values may appear in request logs, exception traces, temporary multipart files, metrics labels, crash dumps, browser storage, or platform logs. “Verdict summary” is safe only if it excludes raw values and OCR text. Define log redaction and temporary-file behavior explicitly.

## Test-plan gaps

The eight-label M0 set is far too small to tune thresholds or substantiate “never a false PASS.” It is a demo corpus, not an evaluation set.

Missing test dimensions include:

- real camera images separated from synthetic/generated images;
- multiple devices, resolutions, compression levels, glare, blur, perspective, and EXIF rotation;
- multi-column and rotated layouts;
- repeated expected strings and multiple ABV/net-content candidates;
- expected strings assembled accidentally from unrelated tokens;
- one-character legal warning mutations versus one-character OCR errors;
- punctuation-only and capitalization-only warning defects;
- correct warning with low-confidence OCR;
- incorrect warning OCR-normalized into the correct string;
- anchor absent, body present, and anchor/body split across regions;
- very short brand names and class names;
- decimals using commas, fractions, Unicode percent signs, OCR’d units, and proof/ABV rounding;
- invalid or non-finite numeric input;
- CSV encodings, BOMs, embedded newlines, quoted filenames, Unicode normalization collisions, and duplicate filenames;
- browser memory during 300–500 images;
- load, soak, repeated worker crash, model corruption, and pool recovery;
- disconnects, retries, duplicate requests, late responses, and stale-result races;
- shutdown/redeploy with jobs in flight;
- accessibility during rapid streaming updates, not only static pages.

Snapshotting OCR expectations also risks freezing engine mistakes as approved behavior. Golden tests should track semantic outcome, transcription quality, and calibrated uncertainty separately.

## State-model contradictions

Several definitions still disagree:

- Government warning is always checked, yet an all-`NOT CHECKED` record is specified.
- “Absent from label” appears as a `NEEDS REVIEW` reason even though readable absence is defined as `MISMATCH`.
- A failed batch item is called a “red row,” but system failures belong to the amber/incomplete family, not mismatch red.
- “Overall status is worst field” conflicts with the later two-axis model.
- “No mismatch found” can coexist with unreadable checks and may be misunderstood as reassurance.
- A global OCR timeout cannot preserve independently completed fields unless field checks are separately staged or OCR already completed; nearly all fields depend on the same OCR result.
- Editing application data while a request is in flight needs versioning. Otherwise a late response can be displayed against newer input despite the stale-result rule.

Use an explicit record state machine and attach an immutable input revision/hash to every request and response.

## Recommended gates before implementation

M0 should not pass merely because OCR looks plausible on eight images. It should require:

1. A measured deployment topology that fits memory and meets latency on the intended host.
2. A specified geometric token-reassembly and candidate-ranking algorithm.
3. Field-specific threshold curves with an ambiguity policy.
4. A defensible distinction among mismatch, not visible, and unreadable.
5. Character-level uncertainty handling for statutory text.
6. Evidence that bold classification is useful—or removal of automated yes/no bold verdicts.
7. A 300-item browser/server load test including memory, queueing, cancellation, and retries.
8. Real-label test data with independently annotated ground truth and explicit false-match ceilings.

Until those are resolved, the most dangerous claims in the plan are “OCR is verbatim by construction,” “high confidence permits absence → mismatch,” “exact-match warning,” “2 GB with workers = cores,” and “CRITICAL GAPS: 0.”
