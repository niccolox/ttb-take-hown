# Document Intelligence Pipeline — Upload → OCR → VLM (Nemotron Nano VL on Azure)

Research date: 2026-08-02. Question: architecture for a layered document
intelligence pipeline — document upload, OCR, and a vision-language
model — using Nemotron Nano VL hosted on Azure, applied to Label Check.
Sources: HF model cards + NVIDIA blogs/docs, Microsoft Foundry/Learn
pages, Azure Retail Prices API (2026-08-02 snapshots), industry pattern
write-ups — URLs at end. Companions: `nemotron-pipeline-architecture.md`
(the two-tier async design this extends), `nvidia-ocr-lineage-azure.md`
(this doc REFINES its VLM lineage claim), `hosting-economics-two-vs-one-
container.md`, TODOS "VLM assist" + "Application-side ingestion".

## Part 1 — Which Nano VL (and the supply-chain answer)

| Model | Params/ctx | Backbone | Disclosed PRC exposure | Single-GPU fit |
|---|---|---|---|---|
| **Llama-3.1-Nemotron-Nano-VL-8B-V1** | 9B / 16K | Llama-3.1-8B (US) + C-RADIOv2-H (teachers: DFN-CLIP, OpenAI CLIP, DINOv2, SAM — US) | **None on card** — synthetic data "generated programmatically", no Qwen mention | FP16 ~18 GB → **A10 24 GB OK**; FP4-QAD variant exists |
| Nemotron-Nano-12B-v2-VL | 12.6B / 128K | Nemotron hybrid Mamba2 (NVIDIA, from scratch) | Backbone post-training + VL annotations from **Qwen3-235B, Qwen2.5-72B/32B/14B, DeepSeek R1** (disclosed) | BF16 ~25 GB → needs L40S/A100; **no L40S SKU exists on Azure** |
| Nemotron 3 Nano Omni 30B-A3B (2026-04) | 31B MoE / 256K | Nemotron 3 Nano + C-RADIOv4 | "Improved using **Qwen3-VL-30B, Qwen3.5-122B/397B, Qwen2.5-VL-72B**, gpt-oss-120b" — heaviest | FP8 33 GB → L40S/A100 |

**Refinement of the earlier lineage research:** "all Nemotron VLMs carry
Qwen asterisks" is too coarse — the asterisks are per-model. The
**8B-V1 is the pick for this project**: cleanest disclosed lineage
(weights-derivation AND training-data levels), best Azure/Gov fit, and
still the model NVIDIA claimed #1 on OCRBench v2 at release (856-class
scores; 12B edges it 62.0 vs 60.1 on v2-EN but fails the other two
criteria). All three: open weights, NVIDIA Open Model License,
commercial use allowed (8B adds Llama license pass-through); NVAIE only
applies to the NIM packaging, not self-hosted vLLM.

**Capability caveat that shapes the architecture:** none of the chat VL
models document grounded output (bounding boxes). Our evidence-crop UX
and audit trail REQUIRE boxes — so the VLM can never be the extraction
layer; it reasons over images/crops while OCR anchors every claim
(exactly Azure Content Understanding's grounding design, and NVIDIA's —
grounded extraction is routed to Nemotron Parse 1.1, a 900M
ViT+mBART model that DOES emit boxes + semantic classes; PubTabNet
S-TEDS 93.99).

## Part 2 — Hosting it on Azure

Commercial (East US):
- **Foundry catalog: both Nano VL variants are GA as NIM microservices**
  (managed compute = AML endpoints under the hood; billing = GPU compute
  + NVAIE ~$1/GPU-hr promo). No serverless per-token Nemotron on Azure
  yet ("later this year" per the March 2026 Foundry post).
- **Self-host vLLM (no NVAIE):** 8B FP16 on NV36ads_A10_v5 ($3.20/hr
  PAYG, **$0.59 Spot**); 12B needs NC24ads_A100_v4 ($3.673 / $0.679
  Spot — A100 Spot is barely above A10 Spot, best price/perf if the 12B
  were wanted).
- Third-party per-token exists (~$0.20/M in, $0.60/M out; OpenRouter
  free tier) — none FedRAMP; fine for dev experiments only.

Azure Government (usgovvirginia):
- **Foundry in Gov carries Azure OpenAI models ONLY** — no NVIDIA/NIM
  catalog. Route = self-service vLLM/NIM on AML (FedRAMP High / IL5
  scope) or AKS.
- **The only single-GPU Gov SKU is NV36ads_A10_v5 ($4.00/hr PAYG,
  $0.739 Spot)** — the 8B fits it; the 12B's next Gov step is 8×A100 at
  $34/hr. The 8B-V1 pick is effectively forced in Gov, and happily it's
  also the clean-lineage pick.
- No FedRAMP per-token Nemotron exists anywhere; the FedRAMP per-token
  VLM alternatives are Azure OpenAI in Gov (GPT-4o/4.1/5.1) — relevant
  only if the no-cloud-ML premise were ever re-gated.

**Co-location economics (the punchline):** OCR v2 English (1.6–2.2 GiB)
+ Nano VL 8B FP16 (~18 GiB) fit ONE A10 24 GB together. One
NV36ads_A10_v5 hosts the entire document-intelligence stack — app
container, OCR sidecar, VLM sidecar — at $0.59/hr Spot commercial /
$0.74 Gov. Against the hosting-economics doc: the VLM layer adds ZERO
marginal hosting cost to the one-GPU-VM shape (it rides the same card),
vs +$331–2,336/mo if it forced its own GPU.

## Part 3 — Reference patterns (what the industry converged on)

- **NVIDIA (NeMo-Retriever):** OCR and VLM are distinct swappable layers
  selected per document (`extract_method`: pdfium / pdfium_hybrid / ocr
  / nemotron_parse). Specialist models for tables/charts; VLM parse
  costs +1 GPU +16 GB and loses the chart modality — even NVIDIA doesn't
  VLM-everything.
- **Azure Content Understanding (GA `2025-11-01`)** is Microsoft's
  productized version of exactly our design: OCR content extraction →
  LLM field extraction (Extract = verbatim, Classify, Generate) → a
  contextualization layer computing **source grounding + calibrated 0–1
  confidence** (`estimateFieldSourceAndConfidence`) to enable
  straight-through processing. Azure DI meters: Read $1.50/1k pages,
  Layout $10, custom generative $30.
- **Hallucination numbers justify OCR-primacy:** specialized OCR 93.2%
  hallucination-free vs general VLMs 72.6–85.0% (PP-OCRv6 bench);
  canonical failure is "contextually plausible, factually wrong"
  ($42.50→$45.20). For statutory text verification that failure mode is
  disqualifying — **the VLM must never override OCR on exact-text
  checks.**
- **Named hybrid patterns:** VLM-as-fallback (tiered escalation on
  confidence — our L5), VLM-as-structurer (VLM structure + OCR text
  wins on critical fields — the COLA-form ingestion fit),
  VLM-as-verifier (cross-check on uncertainty). Async norm across
  Azure/AWS/Google: 202 + poll (Operation-Location) or job-id + fetch —
  our `result_id` design from the pipeline doc is the industry shape.

## Part 4 — The Label Check pipeline with the VLM layers placed

Extends the two-tier architecture (fast path <5s + background layers);
stages S0–S2 and L2–L4 unchanged from `nemotron-pipeline-architecture.md`.

```
upload (exists: POST /api/verify, multi-panel)
  ─► S0 intake: decode, EXIF, deskew, panel classify
  ─► S1 OCR fast path: nemotron-ocr-v2 word-level (~250 ms) — sole grounding source
  ─► S2 locate + verify → provisional result + result_id      [<5 s hard, ~0.6 s measured]
background layers:
  L2 crop re-OCR escalation (verified fix for small-print dropout)
  L3 cross-engine check (paddle ↔ nemotron, E4 telemetry)
  L4 region quality / weight-contrast
  L5 VLM assist — Nano VL 8B, THREE roles, all OCR-grounded:
     (a) fallback reader: flagged/unreadable fields get the located CROP
         + question ("what does the net contents statement say?");
         answer only ever upgrades to NEEDS_REVIEW-with-suggestion,
         never to MATCH on statutory text (hallucination data, Part 3)
     (b) verifier: second opinion on locator disagreements (label_value
         vs VLM read of the same crop; disagreement stays NEEDS_REVIEW)
     (c) structurer: COLA form/PDF ingestion (TODOS P2 "application-side
         ingestion") — form image → JSON application fields, human
         confirms; VLM structure + OCR verbatim text on critical fields
  L6 (optional, later): Nemotron Parse 1.1 for grounded layout classes
     (Table/Section-header/Caption + boxes) — richer panel understanding
     and table-form COLA ingestion; 900M fits anywhere
merge: conservative tier-merge (never _MERGE_RANK), full provenance
```

Hard rules carried into the VLM layers: (1) OCR boxes are the only
evidence source — every VLM claim renders with the OCR crop it was
asked about; (2) VLM outputs are suggestions or verifications, never
autonomous MATCH/MISMATCH on §16.21 text; (3) crops in, not full
labels — smaller hallucination surface, and it matches the 512×512×12-
tile input scheme; (4) all VLM calls are background jobs (5–15 s VLM
latency never touches the interactive path).

## Part 5 — Deployment shapes and cost

| Shape | Stack | Cost (mo, 730h where flat) |
|---|---|---|
| Dev laptop (this machine) | app + OCR sidecar; VLM via build.nvidia.com free tier (rate-limited, non-sensitive test images only) | $0 |
| Commercial pilot | ONE NV36ads_A10_v5 Spot: app + OCR + vLLM Nano VL 8B FP16 | **~$431 PAYG→$61–432 Spot-dependent; Spot ≈ $431×0.185 ≈ $80** |
| Commercial, VLM rarely used | split per economics doc: B3 app + ACA T4 OCR + VLM **on-demand Spot VM started per batch** | $73–239 + VLM hours × $0.59 |
| Gov | ONE NV36ads_A10_v5 usgovvirginia: everything on it | $2,920 PAYG / **$540 Spot** |
| Foundry NIM route | managed endpoints, 2 GPUs (OCR NIM + VLM NIM) + NVAIE | ~2×(compute+$1/hr) — pays for management, loses co-location |

(4 GB local card cannot host the 8B even quantized alongside OCR — the
laptop profile stays OCR-only, VLM development against the free NVIDIA
API endpoint with synthetic/golden images only, per the sensitive-image
constraint.)

## Explicitly unverified

- Nano VL 8B FP16 + OCR v2 actually co-resident on one A10 24 GB under
  load (arithmetic says ~20 GiB total; KV-cache headroom at 16K context
  untested).
- 8B-V1 "no Qwen mention" is a disclosure claim, not a negative proof —
  NVIDIA doesn't enumerate synthetic-data generators for it.
- VLM crop-QA accuracy on OUR label crops (needs a golden-style eval
  before L5 ships; the M1 harness extends naturally).
- Azure serverless per-token Nemotron timing ("later this year").
- Nemotron Parse 1.1 quality on label layouts (built for documents).

Sources: huggingface.co/nvidia/{Llama-3.1-Nemotron-Nano-VL-8B-V1,
NVIDIA-Nemotron-Nano-12B-v2-VL-BF16, Nemotron-3-Nano-Omni-30B-A3B-
Reasoning-BF16, NVIDIA-Nemotron-Nano-12B-v2, nemotron-ocr-v2,
NVIDIA-Nemotron-Parse-v1.1} · arxiv 2511.03929, 2604.24954, 2511.20478,
2606.13108 (PP-OCRv6 hallucination bench) · github.com/NVlabs/RADIO ·
ai.azure.com/catalog (NVIDIA NIM microservice listings) ·
techcommunity.microsoft.com Foundry blog posts (NIM availability,
March 2026 Nemotron-on-Foundry) · learn.microsoft.com (Content
Understanding overview, Document Intelligence v4.0, Foundry-in-Gov
model list, FedRAMP audit scope, NC/NV family sizes) · Azure Retail
Prices API snapshots 2026-08-02 · docs.nvidia.com/nemo/retriever
(extraction, multimodal-extraction) · developer.nvidia.com blog
(Nemotron Parse 1.1, Nano VL OCRBench) · build.nvidia.com ·
slavadubrov.github.io OCR guide 2026 · openrouter.ai · aipricing.org.
