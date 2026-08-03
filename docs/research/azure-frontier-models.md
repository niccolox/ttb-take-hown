# Azure Frontier Models × Label Check — Job-Spec-Driven Opportunities (2026-08-03)

Job spec: docs/plans/IT-Specialist -AI.md — IT Specialist (AI), Treasury
Departmental Offices, GS-15. Three duties: (1) formulate enterprise AI
engineering strategies/standards for AI-enabled systems and cloud-native
architectures under federal mandates; (2) design and evaluate secure AI
deployments with cybersecurity-by-design and DevSecOps; (3) lead
cross-agency AI projects — large-scale transformation, data platforms,
secure computing.

Sources (fetched 2026-08-03): Azure Government dev blogs (Azure OpenAI
FedRAMP High for Azure Government incl. GPT-4o; authorization across US
government data classification levels), Microsoft public-sector tech
community (FedRAMP practicality), OpenAI (ChatGPT Gov), industry trackers
on FedRAMP AI model availability.

## The landscape fact that shapes everything

Two boundaries, different frontiers:

- **Azure Government** (FedRAMP High, isolated): Azure OpenAI authorized,
  but the model catalog **trails** — GPT-4.1 / o3-mini class as of early
  2026. This is where pre-approval COLA data could lawfully go.
- **Azure Commercial / AI Foundry** (FedRAMP High authorization boundary,
  not the isolated cloud): carries true frontier models — GPT-5.x and
  **Anthropic Claude Opus/Sonnet 4.6** — with tenant isolation and
  no-training-on-inputs terms.

So "integrate Azure frontier models" is really a **model-placement
standard** — deciding which data classes may meet which boundary. That
decision artifact is duty (1) verbatim, and Label Check already has the
FIPS 199 categorization (Confidentiality MODERATE for pre-approval label
data, docs/deploy-security.md) to anchor it.

## The placement standard (proposal)

| Data class | Examples | Permitted boundary | Models |
|---|---|---|---|
| Synthetic / golden / public reference | goldens, BAM samples, anatomy labels, TTB guidance text | Commercial Foundry | GPT-5.x, Claude 4.6 (frontier) |
| Pre-approval label data (Conf. MODERATE) | real COLA images + registry values | Azure Government only | GPT-4.1 / o3-mini class |
| Statutory verdict path | §16.21 text compare, ABV bands | **no model, any boundary** | rules engine only |

The third row is load-bearing: frontier models never enter the verdict
path — the ratified posture (assistive output cannot change a field
status; agent decision primacy is enforced in code) survives every
opportunity below.

## Opportunities (mapped to existing seams)

**A1 · Activate J4 — the seam already exists (milestone N6).** The
enrichment plan ratified an Azure-hosted LLM as a non-blocking background
layer with silent-degrade offline (decision D3). Frontier use: a
structured second-opinion on *ambiguous* field comparisons only — brand
tie-breaks the locator flags as ambiguous, class/type alternates,
diacritics cases — returning suggestion-only annotations in the J3
pattern (`test_j3_attaches_suggestion_without_status_change` is the
enforcement precedent). One env pair (endpoint + key) turns it on;
absence keeps byte-identical offline behavior. *Job-spec fit: duty 2 —
secure deployment of an AI layer that fails closed.*

**A2 · Frontier VLM for the hard reads (J3 alternative).** J3 currently
targets NVIDIA-hosted Nano VL, crops-only. Foundry's multimodal frontier
models (GPT-5.x vision, Claude 4.6) are substantially stronger on the
reads that defeat OCR: script fonts (the BAM 'Fanciful Name Rose'
italic), curved badge text (MALT & HOP's 'BREWED & BOTTLED' arc), pearl
foil / low-contrast metallics. Same contract: crops only, never full
labels, suggestion-only, dev tier against goldens until the placement
standard clears more. The provider becomes a config choice — which is
exactly the multi-vendor posture Treasury's acquisition direction favors.

**A3 · Guidance-grounded class/type assist (RAG over what we ingested).**
The repo now holds TTB's own guidance corpus (wine/malt/spirits audits,
anatomy explanation texts, BAM chapter). A frontier model with that
corpus as grounding can flag application-side class/type problems the
rules engine can't adjudicate: "'IPA' alone is not a recognized class —
qualify with ale/beer (§7.146)"; statement-of-composition plausibility
for specialties. Suggestion-only row annotations with the citation the
grounding retrieved. *Duty 1: standards encoded as running software.*

**A4 · Batch brief.** After a 300-label batch settles, a background job
drafts the reviewer's memo: counts by disposition, recurring defect
patterns ("9 labels share the same title-case warning plate"), outliers
worth first attention. Narrative only — every number recomputed from the
result store, the model writes prose around verified figures. *Duty 3:
the large-scale-review transformation story.*

**A5 · Agent copilot on the runbook + reference corpus.** Train-before-
pilot extension: a Q&A box grounded on runbook.html + the ingested TTB
guidance, answering "does this wine need an appellation?" with the §4.27
citation. Read-only, never sees label images, cites or declines.

**A6 · Correction-letter drafts.** A red verdict already carries diff
boxes and citations; a frontier model can draft the needs-correction
narrative ("the warning prints 'birth defect' where §16.21 requires
'birth defects'…") for the agent to edit. Draft-only, statutory text
quoted never paraphrased.

## Guardrails that do not move

Cloud AI off by default and **silent-degrade** (D3) — byte-identical
behavior offline, proven by the no-egress check. Crops-only for anything
multimodal. Suggestion-only: no model output mutates a status. `.env`
server-side, never in images (deploy-security). The statutory comparison
stays exact-match rules code at any model tier. Telemetry stays local.

## Sequencing

1. **A1** is one design doc + ~a day: the J4 stub, flags, and D3
   semantics are ratified; needs Azure OpenAI endpoint + key (N6's gate).
2. **A2** rides J3's existing crops-only client with a second provider.
3. **A3/A5** share one grounding corpus build (the audits already
   curated it); A5 is the cheaper proof.
4. **A4/A6** are output-formatting layers over existing result data.
5. The **placement standard** (table above) should land first as a page
   in docs/ — it is the artifact the job spec's duty (1) describes, and
   every opportunity cites it.

## Job-spec traceability (for the cover story)

- Duty 1 (strategies/standards/cloud-native, federal mandates): the
  model-placement standard; FIPS 199 anchoring; dual-boundary
  architecture; AI RMF mapping already in docs/ai-risk-statement.md.
- Duty 2 (secure deployment, cybersecurity-by-design, DevSecOps): D3
  fail-closed design; no-egress proof in CI; hash-locked supply chain +
  SBOM; suggestion-only enforcement as tests, not policy prose.
- Duty 3 (cross-agency scale, data platforms): batch physics (300-label
  sets), dual-engine QA telemetry as a standing calibration dataset,
  and the pilot-evidence loop (train-before-pilot T5).
