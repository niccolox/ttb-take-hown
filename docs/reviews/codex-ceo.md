# Codex CEO Voice (strategy challenge) — 2026-07-31

## Strategic blind spots

1. **The plan optimizes for a hypothetical product instead of the hiring exercise.**  
   Batch processing, CSV workflows, concurrency controls, exports, unit conversion, proof cross-checks, accessibility audits, and multiple generated eval sets create a large failure surface. The evaluators explicitly prefer a working core over incomplete ambition. A flawless single-label demonstration with persuasive evidence would likely outperform a broad but brittle pseudo-production system.

2. **“Verification” is being claimed without a trustworthy observation layer.**  
   Moving pass/fail out of the LLM does not make the system deterministic. Every rule still depends on probabilistic extraction. If the model silently changes capitalization, punctuation, units, or wording, deterministic comparison merely produces a confidently wrong result. The architecture is auditable after extraction, not reliably correct.

3. **Prompting is not a credible mitigation for the central false-PASS risk.**  
   “Do not correct errors” cannot guarantee character-exact transcription. A golden set can reveal known failures but cannot establish that an LLM is safe for exact statutory-text or typography verification. The warning requirement calls for OCR with coordinates and image-level evidence, potentially followed by deterministic text comparison—not semantic vision extraction alone.

4. **Bold detection by a vision model is fundamentally mis-scoped.**  
   “Best effort” conflicts with a compliance verifier. If bold is legally required, unverifiable formatting cannot support MATCH. If the prototype cannot measure typography reliably, it should explicitly limit itself to screening and require human confirmation, rather than implying it verifies the warning.

5. **The product’s most important output is missing: visual provenance.**  
   Quoting model-produced text is not evidence. Agents need the exact image crop or bounding box from which each value was read. Without image-grounded highlighting, they must search the label themselves and cannot distinguish faithful extraction from hallucination. A simpler OCR-plus-bounding-box interface may deliver more trust and more workflow value than richer parsing.

6. **The 5-second premise is accepted without validating what it means.**  
   Is that p50, p95, cold-start latency, or time until the first useful result? Does it include upload time on a government network? A “target 2–4 seconds” is not an engineering budget. Vercel cold starts, image transfer, provider latency, retries, and model queueing can easily violate it. A 10-second timeout directly contradicts the stated adoption threshold.

7. **Batch mode makes the latency and reliability assumptions collapse.**  
   Processing 200–300 images through a remote frontier model introduces rate limits, cost, multi-minute completion time, partial failures, retry semantics, and provider quotas. “Bounded parallelism” is not a batch strategy. The plan does not define throughput, cost per batch, resumability, cancellation, duplicate detection, or what happens when the browser closes.

8. **“Apply to all” is probably the wrong primary batch interaction.**  
   A batch of applications will generally contain different brands, ABVs, sizes, and product types. Shared defaults optimize for an atypical case and risk comparing labels against the wrong application. The natural batch unit is a manifest containing one application record mapped to one or more artwork files. File-to-record association is the hard problem, and the plan largely avoids it.

9. **The standalone workflow may save no time at all.**  
   Agents must manually re-enter application fields into a separate tool, upload artwork, wait, then return to COLA. That could be slower than visual checking. The plan measures inference latency but not total task time. A more impactful prototype might accept an application PDF or screenshot and extract both sides automatically, eliminating duplicate entry without requiring COLA integration.

10. **The architecture ignores the clearest infrastructure warning.**  
    Marcus says outbound ML endpoints were blocked and previously caused feature failure. Choosing a cloud-hosted app calling Anthropic is not merely a future production limitation; it undermines the proof of concept’s procurement relevance. The plan should compare at least three deployment paths: browser/local OCR, Azure-hosted inference compatible with the agency environment, and external API inference.

11. **Vercel is strategically misaligned with the stakeholder.**  
    It is convenient for the take-home but demonstrates little about eventual Azure/FedRAMP feasibility. At minimum, the design should isolate the extraction provider behind an interface and show that deployment is portable. Otherwise, the prototype validates an architecture TTB may be unable to adopt.

12. **The plan assumes the wrong compliance source of truth.**  
    The application record is treated as truth and the label as the object being checked. But application data may itself be inconsistent, incomplete, or differently represented. Some checks are label-versus-application; others are label-versus-regulation; others are internal consistency checks. Those are distinct claims and should not be collapsed into one overall “worst status.”

13. **The three-state model is too coarse and semantically confused.**  
    “Absent,” “unreadable,” “low confidence,” “not applicable,” “not supplied,” and “system error” demand different agent actions. NEEDS REVIEW hides whether the applicant must resubmit artwork, the agent must inspect manually, or the system simply failed. A workflow tool should return actionable dispositions, not just severity.

14. **“Never a false PASS” is an impossible and untestable promise.**  
    No vision system can guarantee this. The safer framing is “screening assistant that never grants regulatory approval,” with explicit confidence gates and human confirmation. Calling MATCH or overall PASS risks overstating the prototype’s authority.

15. **Field normalization rules encode policy decisions without authority.**  
    Case-folding and punctuation normalization may be reasonable for “STONE’S THROW,” but the plan generalizes from one anecdote. Punctuation, spacing, diacritics, trademark symbols, or possessives can distinguish legally meaningful brand names. These should be explainable candidate equivalences presented for agent confirmation, not automatic MATCH rules.

16. **ABV and net-content equivalence are oversimplified.**  
    Numeric equality ignores rounding, permitted expression formats, unit precision, beverage-specific exceptions, and conflicting multiple occurrences on front/back labels. Fluid-ounce conversion can introduce rounding disputes. These parsers risk demonstrating confidently invented compliance policy beyond the assignment.

17. **The scope strangely prioritizes proof consistency over stated requirements.**  
    ABV↔proof validation is creative but secondary. It consumes design, testing, and UI attention while foundational issues—multi-image labels, front/back artwork, field localization, and exact transcription—remain unresolved. It looks like feature accumulation rather than prioritization.

18. **The warning text model may be legally incomplete.**  
    The plan assumes one canonical string and whitespace-only normalization without establishing treatment of punctuation, line breaks, paragraph separation, intervening text, legibility, contrast, size, and label placement. “Exact” in the interview should not be converted into a homemade legal rules engine without checking authoritative requirements.

19. **Single-image assumptions are hidden.**  
    Alcohol labels frequently have front, back, neck, or supplemental panels. The plan repeatedly says “the label image,” but the required fields may be distributed across artwork files. This will look naïve immediately if evaluators upload multiple sides.

20. **No abuse or cost controls are specified for the public deployed URL.**  
    A public endpoint backed by a paid vision model needs rate limiting, file-content validation, request-size limits, concurrency caps, budget protection, and possibly CAPTCHA or demo quotas. Otherwise, the deployed deliverable is an exposed API key by proxy and can become unavailable before evaluation.

21. **Client-side compression may destroy the evidence being verified.**  
    Downscaling helps latency but can erase tiny warning text and typography—the exact details central to correctness. The plan needs adaptive resolution or targeted crops, not unconditional compression.

22. **The sample/demo path can conceal rather than prove capability.**  
    Bundled labels risk looking curated, especially if generated images resemble the model’s training distribution. Evaluators will upload their own files. The strongest demonstration would include reproducible failure cases, explicit limitations, and image-grounded evidence, not merely three happy-path buttons.

23. **The plan lacks a baseline.**  
    There is no comparison against commodity OCR, browser OCR, Azure AI Vision, or even manual review time. Without a baseline, Claude is an assumed solution rather than an appropriate technical choice. A hybrid pipeline could be faster, cheaper, more auditable, and more deployable.

24. **The real 10× opportunity is triage, not universal verification.**  
    Trying to verify every field on every label forces the system into legally sensitive edge cases. A more credible product would identify a narrow set of high-confidence, high-volume checks, automatically surface exact image regions, and route everything else to an agent. That can reduce review time without pretending to automate judgment.

25. **The milestones defer the riskiest premise.**  
    M1 should not build the application before proving exact transcription, latency, and image grounding on representative labels. The correct first milestone is a feasibility spike with measured accuracy and latency across clean, small-text, skewed, glare-heavy, and multi-panel examples. If that fails, the entire architecture should change before UI and batch work begin.

The strongest reframe is: build a **human-in-the-loop review accelerator**, not an “AI verifier.” Extract only a few high-value fields, highlight their source regions on the artwork, distinguish regulatory checks from application comparisons, measure end-to-end time saved, and refuse automated conclusions when observation is uncertain. That would be narrower, more defensible, and far more relevant to eventual adoption.
