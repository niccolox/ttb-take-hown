# PRC-Free NVIDIA OCR on Azure: Deep Lineage + Deployability Compare

Research date: 2026-08-02. Question answered: **of the NVIDIA models on
Hugging Face, which OCR options are free of PRC supply-chain risk — is it
Nemotron OCR? — and what is the best USA OCR model that can realistically be
deployed on Azure?** Compiled from two parallel research passes: a
training-chain lineage audit of the HF model cards + tech reports, and an
Azure deployability/pricing pass (live Azure Retail Prices API queries,
Foundry catalog checks). Companion docs: `nvidia-open-ocr.md`,
`ai-supply-chain-risk.md`.

Risk taxonomy used throughout:
**(a)** PRC-origin MODEL in the chain (weights, teacher, or synthetic-data
generator — the real supply-chain concern) ·
**(b)** PRC-origin public DATASET (disclosable, lesser) ·
**(c)** UNDISCLOSED (unknown risk).

---

## TL;DR — direct answer

**Yes, it's Nemotron OCR v2 — with one honesty clause and one Azure
surprise.**

- **Lineage**: Nemotron OCR v2 is *structurally* the lowest-supply-chain-risk
  OCR NVIDIA ships — a from-scratch RegNet CNN + Transformer with **no base
  weights, no teachers, no synthetic-data generator models named anywhere**,
  and nothing PRC in any disclosed element. The honesty clause: its training
  datasets are unnamed ("public and proprietary mix"), so the verdict is
  **"clean in every disclosed element (category c residual)"** — not
  "certifiably clean." Its Chinese-language capability comes from
  programmatically *rendered* synthetic pages, not PRC models.
- **Azure surprise**: the Image OCR NIM is **not in the Azure AI Foundry
  catalog and has no Azure Marketplace offer** — nemotron-ocr-v2 on Azure is
  **DIY-container only** (which is fine: it's an ~84M open-weights pip
  package). Meanwhile **Nemotron Parse IS a one-click GA Foundry catalog
  entry** — so if "realistically deployed on Azure" means one-click,
  **Nemotron Parse v1.1 NIM is the practical winner**, and it shares the
  clean disclosed model chain (C-RADIO + Meta-lineage mBART decoder).
- **Best USA OCR model realistically deployable on Azure, final ranking**:
  1. **Nemotron OCR v2** — DIY container (AML managed endpoint or ACA
     serverless GPU); cheapest *supported* config ≈ fractional A10
     (~$663/mo always-on) or ACA serverless A100 (~$120-200/mo at low
     volume). Best accuracy-per-param, fastest (34.7 pages/s on A100),
     cleanest structural lineage.
  2. **Nemotron Parse v1.1 (NIM on Foundry)** — one-click, GA, doc parsing
     with bboxes/reading order; VM + ~$1/GPU-hr NVAIE surcharge.
  3. **IBM Granite-Docling-258M** — also a Foundry catalog entry, Apache-2.0,
     **the cleanest disclosure in the entire audit** (every dataset AND
     generator named, all US/EU); trails on peak accuracy. The
     transparency-first pick.
  4. VLM tier (field extraction, not raw OCR): Nemotron Nano 2 VL — best
     capability but carries a **confirmed Qwen asterisk**; a policy call.

---

## 1. The lineage audit (Hugging Face cards + tech reports)

| Model | Base/teacher ancestry (as disclosed) | Training data disclosure | PRC exposure | Verdict |
|---|---|---|---|---|
| **nemotron-ocr-v1** ([card](https://huggingface.co/nvidia/nemotron-ocr-v1)) | none claimed — from-scratch RegNetY + Transformer | "large-scale curated mix of public and proprietary OCR datasets" — zero names | none disclosed | **UNDISCLOSED** (nothing PRC — but little disclosed at all) |
| **nemotron-ocr-v2** ([card](https://huggingface.co/nvidia/nemotron-ocr-v2)) | none claimed — from-scratch RegNetX + Transformer (char vocab, no LLM tokenizer) | ~680K real images by *category* (scene text, tables, handwriting) + ~11M+ **programmatically rendered** multilingual synthetic pages; no dataset names | none disclosed; ZH data is rendered, not model-generated; OmniDocBench (Shanghai AI Lab) used for **eval only** (category b, benchmark) | **UNDISCLOSED, leaning clean** — structurally the lowest category-(a) risk in the catalog |
| **Nemotron Parse v1.1/v1.2** ([v1.2](https://huggingface.co/nvidia/NVIDIA-Nemotron-Parse-v1.2)) | C-RADIO (NVIDIA) + **mBART decoder (Meta)**; tokenizer carries Meta Galactica/Nougat scientific-token fingerprints ([START_SMILES] etc.) | "internal datasets: human, synthetic, automated"; no names | none disclosed; mBART's distant CC25 corpus includes Chinese Common Crawl text (category b, ancestor-level) | **CLEAN on model chain, UNDISCLOSED on data** |
| **C-RADIOv4-H** ([card](https://huggingface.co/nvidia/C-RADIOv4-H)) | teachers **named on-card**: google/siglip2-giant, facebook/dinov3-vit7b16, facebook/sam3; data = NV-CC-Img-Text 700M | fully named | none | **CLEAN — best-documented model in the audit** |
| **C-RADIOv2-H** ([card](https://huggingface.co/nvidia/C-RADIOv2-H), [RADIOv2.5 paper](https://arxiv.org/abs/2412.07679)) | teachers per cited paper: DFN CLIP (Apple), OpenAI CLIP, DINOv2 (Meta), SAM-H (Meta), later SigLIP (Google) | NV-CC 700M | none | **CLEAN per cited lineage** (teachers on paper, not card) |
| **Llama-3.1-Nemotron-Nano-VL-8B** ([card](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1)) | Llama-3.1-8B (Meta) + C-RADIOv2-H — US weights | "NV-Pretraining / NV-CosmosNemotron-SFT," no generator names | **Eagle-lineage asterisk**: NVIDIA's own [Nano V2 VL report](https://arxiv.org/abs/2511.03929) places it in the Eagle 2/2.5 line — whose sibling models use **Qwen2.5 backbones** ([Eagle 2](https://arxiv.org/abs/2501.14818), [Eagle 2.5](https://arxiv.org/abs/2504.15271)), whose data pool includes PRC datasets (Ruozhiba, Chinese-Meme) and unnamed VLM-generated captions | **CANNOT BE CERTIFIED CLEAN** |
| **Nemotron Nano 2 VL 12B** ([FP8 README](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8)) | NVIDIA from-scratch hybrid backbone + C-RADIOv2-H | partially named | **confirmed**: "Some datasets were improved with **Qwen2.5-72B-Instruct** annotations" (~30% of corpus model-assisted); text base also discloses Qwen reasoning traces | **ASTERISK (category a, data-generation)** |
| **Nemotron 3 Nano Omni 30B** ([card](https://huggingface.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16)) | NVIDIA from-scratch MoE + C-RADIOv4-H | detailed | **confirmed, heavy**: "improved using Qwen3-VL-30B…, Qwen3.5-122B/397B, Qwen2.5-VL-72B, gpt-oss-120b"; its **"CC for OCR" training set was generated with DeepSeek OCR + Qwen3.5/Qwen3-VL**; Vision-R1 via GLM-4.1V (Zhipu) | **HEAVY ASTERISK — PRC models generated its OCR training data specifically** |

**Non-NVIDIA US contrast (two findings that reorder the usual assumptions):**

- **Microsoft Florence-2 is dirtier than its reputation**: its FLD-5B data
  engine used **DINO and Grounding DINO from IDEA Research (Shenzhen, PRC)**
  as annotation models ([paper](https://arxiv.org/abs/2311.06242)) — a
  genuine category-(a) exposure. Microsoft TrOCR is clean and unusually
  well-disclosed (BEiT/RoBERTa ancestry, synthetic PDF lines) but is a 2021
  line-level recognizer that is not competitive on modern documents.
- **IBM Granite-Docling-258M has the cleanest disclosure in the audit**:
  every component named (SigLIP2 = Google, Granite 165M = IBM, Idefics3
  arch = HF) and every dataset AND generator named (DoclingMatix ←
  Docmatix, generated by **Phi-3-small, Microsoft**), Apache-2.0
  ([card](https://huggingface.co/ibm-granite/granite-docling-258M)). It
  beats nemotron-ocr on *transparency and license*; nemotron-ocr-v2 beats
  it on capability and speed.

**The lineage ladder (most to least defensible):**
C-RADIOv4-H (fully named, all-US) > Granite-Docling (fully named, US/EU,
Apache) > **nemotron-ocr-v2 / Nemotron Parse** (no PRC in any disclosed
element; data unnamed) > 8B VL (US weights, uncertifiable data lineage) >
Nano 2 VL (confirmed Qwen annotations) > Nano Omni (Qwen/DeepSeek/GLM
generated its OCR data) ≈ Florence-2 (PRC models in the annotation engine).

## 2. Azure deployability (verified against the catalog + live pricing)

### What's actually one-click on Azure AI Foundry (all NIM = managed compute, none serverless)

| Model | Foundry catalog | Path & cost |
|---|---|---|
| **Nemotron Parse NIM** | **YES, GA** ([entry](https://ai.azure.com/catalog/models/NVIDIA-Nemotron-Parse-NIM-microservice)) | Managed compute from A10/A100/H100 SKU list + ~$1/GPU-hr NVAIE surcharge via the single [NIM SaaS Marketplace offer](https://marketplace.microsoft.com/en-us/product/saas/nvidia.nvidia-nims) (90-day surcharge trial) |
| Nemotron Nano 12B v2 VL NIM | YES, GA ([entry](https://ai.azure.com/catalog/models/NVIDIA-Nemotron-Nano-12B-v2-VL-NIM-microservice)) | Same mechanics; ~1×A100: $3.67 VM + ~$1 surcharge ≈ **$4.67/hr ≈ $3,400/mo** |
| Llama-3.1-Nemotron-Nano-VL-8B NIM | YES ([Nov 2025 batch](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/nvidia-nim-for-nvidia-nemotron-cosmos--microsoft-trellis-now-available-in-azure-/4463262)) | Same |
| Nemotron 3 Nano / Nano Omni NIM | YES ([June 2026](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/now-in-foundry-ibm-granite-4-1-nvidia-nemotron-nano-omni-and-qwen3-6-35b-a3b/4516858)) | Same |
| **Image OCR NIM (nemotron-ocr)** | **NO** — absent from the catalog, the pay-go supported-NIM table, and all announcement blogs; NGC/build.nvidia.com only | **DIY only** (below) |
| IBM Granite-Docling-258M | **YES** ([entry](https://ai.azure.com/catalog/models/ibm-granite-granite-docling-258m)) | Managed compute, **no NVAIE surcharge**, Apache-2.0; runs on the smallest GPU SKUs |

### The DIY path for nemotron-ocr-v2 (the fine print that matters)

- It's a pip package that **compiles a CUDA extension at install** (build the
  wheel into the image, not at boot); Python 3.12, Linux, GPU required.
- **Supported hardware is Ampere+ (A10G, L4, L40S, A100, H100…) — Turing T4
  is NOT on the list.** And **Azure sells no L4 or L40S VMs at all** — the
  2026 lineup is T4 / A10 (incl. fractional) / A100 / H100+. So:
  - Cheapest **supported** always-on: **NV12ads_A10_v5 (⅓ A10, 8 GB) at
    $0.908/hr ≈ $663/mo** — the 84M model fits easily.
  - Cheapest overall: NC4as_T4_v3 ≈ $384/mo, but Turing is off-list —
    unsupported risk.
  - **Best low-volume fit: Azure Container Apps serverless GPU** (GA; T4 and
    A100 profiles, per-second billing, scale-to-zero, 1-3 min cold starts) —
    at ~1 GPU-hr/day: **~$120-200/mo** (estimate). A100 profile avoids the
    T4 support question.
- vLLM-serving Nano 2 VL on Azure: the FP8 sweet spot (L40S) doesn't exist
  on Azure; the realistic SKU is **NC24ads_A100_v4 ($3.67/hr ≈ $2,680/mo
  PAYG, ~$1,700-1,900/mo reserved)** — and it can co-host nemotron-ocr-v2 on
  the same 80 GB card.

### Azure Government (the Treasury-relevant part)

- Foundry exists in US Gov Virginia/Arizona (FedRAMP High/IL5) but the gov
  model catalog is a small curated set: **no NVIDIA collection, no NIMs, no
  Marketplace NIM path** ([cloud parity doc](https://learn.microsoft.com/en-us/azure/machine-learning/reference-machine-learning-cloud-parity)).
- Gov GPU reality: A10s are the workhorses (usgovvirginia NV12ads $1.135/hr
  ≈ $829/mo); **no single-GPU A100/H100 exists in gov** (only 8-GPU ND
  boxes at $34-123/hr).
- **The FedRAMP-High path for PRC-free NVIDIA OCR is exactly one thing: the
  DIY nemotron-ocr-v2 container on A10 (AML managed endpoint or AKS) in
  usgovvirginia.** NIMs would require BYOL NVAIE on hardware the gov
  regions don't sell in single-GPU form. Azure Document Intelligence
  (Microsoft's own, gov-hosted, no NVIDIA involvement) remains the
  zero-ops alternative at ≈$1.50/1k pages.

## 3. The verdict, assembled

**Best USA OCR model, PRC-supply-chain-free, realistically deployable on
Azure: NVIDIA Nemotron OCR v2.** It pairs the strongest structural lineage
argument (from-scratch, no model ancestry anywhere, nothing PRC disclosed,
NVIDIA Open Model License) with the best speed/accuracy in its class
(OmniDocBench 0.048 EN edit distance at 34.7 pages/s; NVIDIA-benchmarked
above PaddleOCR v5 and EasyOCR) — and a genuinely cheap Azure path because
it's an 84M-param pip package, not a NIM: fractional A10 (~$663/mo
always-on), ACA serverless A100 (~$120-200/mo low-volume), or co-hosted on
a bigger card. It is also the only NVIDIA OCR option deployable in **Azure
Government** without NVAIE gymnastics.

Qualifiers, ranked by how much they should sway a decision:
1. **If one-click Foundry deployment is a requirement**, use **Nemotron
   Parse v1.1 NIM** (GA catalog entry, clean disclosed model chain,
   bbox+reading-order output) and accept the ~$1/GPU-hr surcharge.
2. **If auditable transparency outranks peak accuracy** (a plausible
   Treasury posture), **Granite-Docling-258M** is the only model in this
   audit whose entire training chain is named — and it's in the Foundry
   catalog under Apache-2.0 with no surcharge.
3. **If VLM field extraction is needed**, no NVIDIA VLM is asterisk-free:
   Nano 2 VL (best fit) has confirmed Qwen2.5-72B annotations; the 8B VL
   has uncertifiable Eagle lineage; Nano Omni's OCR training data was
   generated by Qwen/DeepSeek/GLM. Choose between the documented asterisk
   (12B, best capability) or falling back to Azure Document Intelligence /
   Phi-4-multimodal (Microsoft-native). This is a policy call, not a
   technical one — record it at the premise gate.
4. **Scene-text caveat for this project**: nemotron-ocr-v2's published
   numbers are document benchmarks; the card lists natural-scene and
   arbitrary-shaped text in training, but **label-photo performance is
   unproven — the M1 eval on api/eval/colacloud corpora remains the
   decision data** (PLAN-us-stack.md).

## Caveats

- "Clean in every disclosed element" ≠ certified clean: nemotron-ocr and
  Parse withhold dataset names; an agency requiring provable data
  provenance should prefer Granite-Docling or demand disclosure from NVIDIA.
- Pricing from live Retail Prices API queries (2026-08-02, eastus2 +
  usgovvirginia/arizona PAYG) and the Learn pay-go doc (updated
  2026-06-16); the ~$1/GPU-hr NVAIE surcharge is labeled promotional.
- Foundry catalog contents move monthly — re-verify entries before
  procurement; the Image OCR NIM's absence was checked against the catalog
  URL pattern, the supported-NIM table, and announcement blogs on the
  research date.
- NVIDIA Open Model License guardrail-termination clause applies to all
  Nemotron models (see `nvidia-open-ocr.md` §2).
