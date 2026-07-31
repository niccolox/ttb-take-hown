# Top 10 Success Strategies, Tactics, and Operations for OCR Projects

Researched 2026-07-31. The inverse of `ocr-project-failure-modes.md`: what production OCR/document-AI systems that work actually do, from production engineering retrospectives, document-AI architecture papers, and eval-ops practice. Grouped as **strategy** (what to decide), **tactics** (what to build), **operations** (what to run), with a closing map to this repo's PLAN.md.

---

## Strategy

### 1. Decide what the document task actually is — recognition, or understanding

"OCR in 2026 is document understanding, not only character recognition. Classical OCR is still useful when the input is clean and format is stable, but VLMs are better when layout, tables, handwriting, or semantic extraction matter" ([Edge of Context OCR guide](https://slavadubrov.github.io/blog/2026/03/04/ocr-guide/)). The winning move is a deliberate engine-per-requirement choice — and for verbatim-fidelity tasks (statutory text, IDs, amounts), classical OCR's character-exactness beats a VLM's fluency. Pick per constraint, not per fashion.

### 2. Don't OCR what doesn't need OCR

"One of the biggest mistakes in production OCR systems is running OCR on every PDF blindly — many PDFs already contain embedded selectable text" ([Preocr best practices](https://preocr.io/blog/ocr-best-practices-in-2026-how-to-build-a-production-ready-ocr-pipeline)). Generalized: route by input type first (born-digital vs scan vs photo), and spend the expensive path only where it's needed. Cheapest accuracy gain available.

### 3. Involve domain experts before the first label

"Involving domain experts early in the labeling process reduces the number of training iterations needed to reach production quality and catches semantic errors that wouldn't appear in standard accuracy metrics" ([Kili, OCR data labeling](https://kili-technology.com/blog/ocr-annotation)). The compliance agent, not the engineer, knows which mismatches matter — encode that judgment into the ground truth from day one.

### 4. Design the human-review loop as a product surface, not an exception handler

Confidence-threshold routing into review queues is the architecture, not the fallback: "review queues must present extracted data, confidence indicators, and rule failures in a way that supports fast and accurate correction" ([HealthEdge pipeline architecture](https://healthedge.com/resources/blog/building-a-scalable-ocr-pipeline-technical-architecture-behind-healthedge-s-document-processing-platform), [Devoteam workflow guide](https://www.devoteam.com/expert-view/guide-to-automating-enterprise-workflows-with-ocr-and-ai/)). The economics of the whole system are set by how fast a human can clear a flagged item.

## Tactics

### 5. Preprocess conditionally — it's worth 15-30%, when it's warranted

"Preprocessing alone can improve OCR accuracy by 15-30%" ([Harshith, production pipelines](https://harshith.org/ai-document-processing-ocr-extraction-pipelines-2026/)); restoration-first pipelines like PreP-OCR formalize it ([arXiv](https://arxiv.org/pdf/2505.20429)). But the gain is conditional: engines trained on natural images can *lose* accuracy on aggressively thresholded clean input. The tactic is measured, triggered preprocessing (deskew/denoise when quality metrics demand it) — never one blind pipeline for all inputs.

### 6. Extract field-by-field with validation, not one big pass

"Field-by-field extraction with validation outperforms single-pass extraction for documents with many fields," with structured schemas for parse reliability ([Harshith](https://harshith.org/ai-document-processing-ocr-extraction-pipelines-2026/)). Per-field targeting plus per-field validation localizes errors and lets each field carry its own threshold and rules.

### 7. Embed domain validation rules — math and cross-checks catch what confidence misses

"Embedding mathematical validation rules like (total = sum(items) + tax) can flag discrepancies" independent of OCR confidence ([Harshith](https://harshith.org/ai-document-processing-ocr-extraction-pipelines-2026/)); self-correction loops that validate, feed errors back, and retry deliver ~15% accuracy boosts ([same](https://harshith.org/ai-document-processing-ocr-extraction-pipelines-2026/)). Internal-consistency checks are free accuracy: they detect errors no confidence score can see.

### 8. Handle errors at every stage with a named recovery — never silently

"A production document pipeline handles errors at every stage with appropriate recovery strategies rather than failing silently or catastrophically" ([Harshith](https://harshith.org/ai-document-processing-ocr-extraction-pipelines-2026/)); microservice document-AI architectures make each stage independently retryable and inspectable ([arXiv, operationalizing document AI](https://arxiv.org/html/2605.18818v1)). Every stage gets a failure mode, a user-visible outcome, and a retry path — the error taxonomy is part of the pipeline spec.

## Operations

### 9. Golden datasets + regression gates on every change

"Keep a gold dataset and compare outputs when switching processor versions"; re-evaluate "accuracy drift after new document types… on a golden set" ([DevOpsSchool, Document AI](https://www.devopsschool.com/tutorials/google-cloud-document-ai-tutorial-architecture-pricing-use-cases-and-hands-on-guide-for-ai-and-ml/), [Maxim, golden datasets](https://www.getmaxim.ai/articles/building-a-golden-dataset-for-ai-evaluation-a-step-by-step-guide/)). Human review continuously improves the goldens themselves ([Braintrust](https://www.braintrust.dev/blog/human-review-golden-datasets)). Engine bumps, threshold tweaks, preprocessing changes — nothing merges without the eval gate; version the models *and* the expected outputs.

### 10. Dashboard the four numbers and plan for 3-5x volume

"Dashboards should track documents processed, error rate, average processing time, and alert on spikes in failure rates or unexpected throughput"; "throughput planning should design for 3-5x current expected volume" ([HealthEdge](https://healthedge.com/resources/blog/building-a-scalable-ocr-pipeline-technical-architecture-behind-healthedge-s-document-processing-platform), [arXiv](https://arxiv.org/html/2605.18818v1)). Verdict/error distributions are the drift canary; long-term "drift monitoring and compliance validation become continuous responsibilities" ([Devoteam](https://www.devoteam.com/expert-view/guide-to-automating-enterprise-workflows-with-ocr-and-ai/)).

---

## Mapping to this project

| # | Success practice | PLAN.md implementation |
|---|---|---|
| 1 | Engine-per-requirement | Local OCR chosen *because* verbatim fidelity is the requirement (title-case trap); VLM assist only as gated future option behind `Extractor` |
| 2 | Route by input | Text-mass gate ("doesn't look like a label"); M0 measures raw-vs-preprocessed per image; sample/demo path bypasses nothing |
| 3 | Domain experts in the ground truth | Golden set built from the brief's own trap cases (Jenny's title-case, Dave's apostrophes) + TTB's published label guide (adopted) |
| 4 | Review loop as product | NEEDS REVIEW with reason codes + evidence crops + next-action copy; reviewer-override with audit columns (TODO); amber "you decide" family |
| 5 | Conditional preprocessing | Raw first, corrective pass only on poor confidence (Eng Hardening); EXIF/rotation handling; M0 validates per golden label |
| 6 | Field-by-field + validation | Targeted per-field locator with per-field thresholds and ambiguity margins; per-field verdicts and reason codes |
| 7 | Domain cross-checks | ABV↔Proof internal-consistency rule (proof = 2×ABV); statutory-constant checksum; warning three-outcome model |
| 8 | Errors named at every stage | Section 2 error/rescue map: 0 gaps, every row rescued+tested+visible+logged; system errors never become compliance verdicts |
| 9 | Golden regression gates | M0 harness becomes permanent; snapshot-pinned expectations ("version-bump failures are signal, not flake"); reachability + latency CI assertions |
| 10 | Four-number dashboard, 3-5x headroom | /metrics-lite (count, p50/p95, verdict distribution, errors); worker pool + queue sized from M0 measurement with shed-load behavior |

This completes the six-doc research library: three failure studies (modernization, OCR, government AI) and three success playbooks (modernization, government AI, OCR). The symmetric finding across all six — failures happen at the system and authority layers, successes are built from measured slices with humans deciding — is the thesis PLAN.md was reviewed into.
