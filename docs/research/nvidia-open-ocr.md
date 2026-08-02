# NVIDIA Open OCR: The Best Options as of Mid-2026

Research date: 2026-08-02. Scope: NVIDIA's open-weight OCR and
document-reading models — catalog, benchmarks, lineage, licenses, and
deployment paths — with a fit assessment for this project (Label Check /
PLAN-us-stack.md's escalation tier). Compiled from two parallel research
passes against primary NVIDIA/Microsoft sources; every load-bearing claim
carries a URL. Companion docs: `ai-supply-chain-risk.md`,
`../../PLAN-us-stack.md`.

---

## TL;DR — the picks

1. **Best NVIDIA open OCR engine (dedicated, non-VLM): Nemotron OCR v2**
   (Apr 2026). 53.8M params (EN) / 83.9M (multilingual), detector +
   Transformer recognizer + layout module, **built by NVIDIA to replace
   PaddleOCR** and benchmarked beating it (19.5% lower CER, 34.7 pages/s on
   A100 vs Paddle's 1.2). Open weights on Hugging Face, NVIDIA Open Model
   License, pip-installable standalone. **One catch that matters here: CUDA
   GPU required — no CPU path.**
2. **Best NVIDIA open document VLM (accuracy per dollar): Nemotron Nano 2
   VL 12B** (Oct 2025). OCRBench v2 EN 62.0, DocVQA 94.4; NVIDIA-Open-Model-
   License only (no Llama strings); FP8/NVFP4 checkpoints fit 24/16 GB
   cards; first-class vLLM + guided-JSON; **live in the Azure AI Foundry
   catalog as a NIM** — it is the concrete answer to PLAN-us-stack's PR4.
3. **Top accuracy: Nemotron 3 Nano Omni 30B-A3B** (Apr 2026) — **#2 on the
   official OCRBench v2 leaderboard (65.8 EN), the top open-weight and top
   US entry**, ahead of every Qwen. Costs more VRAM (~25 GB quantized) and
   carries the biggest lineage asterisk (below).
4. **Strict-clean-lineage caveat**: no Nemotron VLM is *initialized* from a
   PRC checkpoint, but **Nano 2 VL and Nano Omni both disclose
   Qwen/DeepSeek models in their synthetic-data/distillation pipelines**.
   If the bar is "no PRC model anywhere in the training chain," the
   defensible set is **Nemotron OCR v1/v2, Nemotron Parse v1.1/v1.2,
   C-RADIO encoders**, and (weights-wise) the Llama-based 8B VL — which
   trades the Qwen asterisk for Llama Community License terms.

---

## 1. The catalog

### Dedicated OCR (small, fast, not VLMs)

| Model | Released | Size | What it is | License |
|---|---|---|---|---|
| **Nemotron OCR v1** ([HF](https://huggingface.co/nvidia/nemotron-ocr-v1)) | Oct 23, 2025 | 52.5M | RegNet detector + Transformer recognizer + relational/layout module; documents AND scene text; vs PaddleOCR: CER −19.5%, bag-of-words error −56.2% | NVIDIA Open Model License (scripts Apache-2.0) |
| **Nemotron OCR v2** ([HF](https://huggingface.co/nvidia/nemotron-ocr-v2)) | Apr 15, 2026 | 53.8M EN / 83.9M multi (EN, zh-Hans/Hant, JA, KO, RU) | Same architecture, deeper recognizer; OmniDocBench edit distance 0.048 EN at **34.7 pages/s (A100)** vs PaddleOCR v5 1.2, EasyOCR 0.4 | NVIDIA Open Model License; commercial-ready |
| **Nemotron Parse v1.2** ([HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-Parse-v1.2)) | Feb 17, 2026 | <1B (C-RADIO ViT-H + mBART decoder) | Document parsing: formatted text + bboxes + semantic classes in reading order; tables as LaTeX/HTML/MD/JSON | Nemotron Open Model License; commercial |
| OCDNet/OCRNet (TAO) ([NGC](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/ocrnet)) | legacy line | small CNNs | Scene-text detect/recognize for DeepStream/edge via nvOCDR C++/TensorRT | Proprietary Model EULA (commercial allowed, not open); **treat as legacy — prefer nemotron-ocr-v2** |

Notes: nemotron-ocr is line-level OCR with reading order — not handwriting
or layout-VQA (that's the VLM tier). NVIDIA's own nv-ingest pipeline
**still ships PaddleOCR as the default OCR NIM** — a US-clean deployment
must explicitly enable `nemoretriever-ocr` instead
([helm README](https://github.com/NVIDIA/nv-ingest/blob/main/helm/README.md),
[RAG blueprint](https://docs.nvidia.com/rag/2.4.0/nemoretriever-ocr.html)).

### Document VLMs (the escalation tier)

| Model | Released | Arch | OCR benchmarks | License |
|---|---|---|---|---|
| **Llama-3.1-Nemotron-Nano-VL-8B** ([HF](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-VL-8B-V1)) | Jun 3, 2025 | Llama-3.1-8B + C-RADIOv2-H, 16K ctx | OCRBench 839; OCRBench v2 EN 60.1; DocVQA 91.2 (#1 OCRBench v2 EN at release) | NVIDIA Open Model License **+ Llama 3.1 Community License** (700M-MAU cap, naming, Meta AUP) |
| **Nemotron Nano 2 VL 12B** ([HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16)) | Oct 28, 2025 | Hybrid Mamba-Transformer (NVIDIA from-scratch) + C-RADIOv2-H, 128K ctx | OCRBench 856; OCRBench v2 EN 62.0; DocVQA 94.4; ChartQA 89.7 ([report](https://research.nvidia.com/labs/adlr/files/NVIDIA-Nemotron-Nano-V2-VL-report.pdf)) | NVIDIA Open Model License only; BF16/FP8/NVFP4 checkpoints |
| **Nemotron 3 Nano Omni 30B-A3B** ([HF](https://huggingface.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16)) | Apr 28, 2026 | Mamba2-Transformer hybrid MoE (~31B total, ~3B active) + C-RADIOv4-H + audio, 256K ctx | **OCRBench v2 2026.06 leaderboard: #2 overall, 65.8 EN — top open-weight entry**, ahead of Qwen3.6/3.5 ([leaderboard](https://99franklin.github.io/ocrbench_v2/)) | Nemotron Open Model License |

No "Nemotron 3 Super/Ultra VL" exists as of Aug 2026 — Nano Omni is the
family's multimodal slot. NVIDIA's OCR progression: 60.1 (Jun 2025) → 62.0
(Oct 2025) → 65.8 (Apr 2026) — the only US open-weight line in the
OCRBench v2 top tier.

## 2. Lineage and license fine print (the part a Treasury review reads)

| Model | Weights ancestry | PRC exposure | Verdict for strict US-clean |
|---|---|---|---|
| Nemotron OCR v1/v2 | NVIDIA-trained CNN+Transformer | none identified | **CLEAN** |
| Nemotron Parse v1.1/1.2 | C-RADIO (NVIDIA) + mBART (Meta arch) | none identified | **CLEAN** |
| C-RADIOv2/v3/v4 | NVIDIA distillation of DINOv2/CLIP/SAM (Meta/OpenAI teachers) | none | **CLEAN** (C- prefix only; plain RADIO is non-commercial) |
| Llama-Nemotron-Nano-VL-8B | Meta Llama-3.1 + C-RADIO | none in weights | CLEAN weights; **Llama Community License** terms attach |
| Nano 2 VL 12B | NVIDIA from-scratch backbone | **synthetic training data generated with Qwen3/Qwen2.5/QwQ and DeepSeek-R1** (tech report) | clean weights, PRC-assisted training data |
| Nano Omni 30B | NVIDIA from-scratch MoE | model card: "improved using" Qwen3-VL-30B, Qwen3.5-122B/397B, Qwen2.5-VL-72B, gpt-oss-120b | clean weights, **heaviest Qwen-in-post-training disclosure** |

**NVIDIA Open Model License caveat (all of the above):** commercial use and
derivatives permitted, royalty-free — but with an **automatic-termination
clause if guardrails are bypassed/disabled/degraded** without substituting
a substantially similar guardrail, plus litigation-termination provisions
([license](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license),
[risk analysis](https://shujisado.org/2025/12/19/nvidia-open-model-license-a-corporate-risk-analysis/)).
For a screening tool that deliberately constrains model output (JSON schema,
field allowlist), this is compatible — we add guardrails, we don't remove
them — but it belongs in the SBOM/license inventory.

## 3. Deployment paths

**The license split that matters:** the *models* are open (HF weights,
self-host on vLLM/llama.cpp in production with **no NVIDIA fee**); the
*NIM containers* are free only for dev/test (Developer Program, 2 nodes/16
GPUs) and require **NVIDIA AI Enterprise (~$4,500/GPU/yr or ~$1/GPU-hr)**
in production
([NIM policy](https://developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members)).
Serving HF weights on vLLM is the fee-free production path.

| Path | Status | Notes |
|---|---|---|
| **vLLM self-host** | First-class for all three VLMs | Nano 2 VL: `vllm serve nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8`; Omni needs `vllm[audio]>=0.20`; guided-JSON structured output is model-agnostic ([vLLM blog](https://blog.vllm.ai/2025/10/31/run-multimodal-reasoning-agents-nvidia-nemotron.html)) |
| **Azure AI Foundry** | **LIVE in catalog**: [Nano 2 VL NIM](https://ai.azure.com/catalog/models/NVIDIA-Nemotron-Nano-12B-v2-VL-NIM-microservice), [8B VL NIM](https://ai.azure.com/catalog/models/Llama-3.1-Nemotron-Nano-VL-8B-v1-NIM-microservice), Nemotron 3 line | Managed-compute deployment (you pick GPU VM SKU) + NVAIE flat per-GPU fee transacted via Azure Marketplace ([MS blog](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/nvidia-nim-for-nvidia-nemotron-cosmos--microsoft-trellis-now-available-in-azure-/4463262), [NVIDIA blog](https://developer.nvidia.com/blog/accelerated-ai-inference-with-nvidia-nim-on-azure-ai-foundry/)). Not serverless per-token. Fee-free alternative: plain vLLM on an Azure GPU VM/AKS |
| **AWS** | SageMaker JumpStart has Nano Omni day-zero + Nemotron 3 line; **Bedrock lacks the VL models** | Azure is the better first-party path for the VL models specifically |
| **build.nvidia.com hosted API** | Free dev tier: 40 RPM (raisable ~200) | `nemotron-nano-12b-v2-vl` and `nemoretriever-ocr-v1` endpoints live; explicitly not for production; OpenAI-compatible, so local-vLLM ↔ remote is a base-URL swap |
| **llama.cpp/GGUF** | Community quants exist (12B VL; official Unsloth for Omni) | **Ollama cannot do vision for these** (mmproj unsupported) — use `llama-mtmd-cli`; hybrid-Mamba GGUF support is newer/rougher |

**Hardware floors:** 8B VL ≈ 19 GB BF16 (AWQ-4bit ≈ **4.8 GB**, runs on
Jetson Orin) · Nano 2 VL 12B ≈ 24 GB BF16 weights → L40S-class; **FP8 fits
24 GB cards, NVFP4 ~7-8 GB fits 16 GB** · Nano Omni ≈ 60 GB BF16 / 35-40
FP8 / ~25 GB Q4. **CPU-only: not realistic for any of them, and
nemotron-ocr officially requires CUDA** — for CPU-only OCR you are back to
Tesseract (or Paddle).

**Latency ballparks** (single image, few-hundred-token JSON; estimates
flagged as such in the research): Nano 2 VL TTFT well under 1 s on
A100/L40S, ~1-3 s total per field extraction; ~2-4 s on a 4090 (FP8/Q4);
~4-8 s on L4/A10. nemotron-ocr-v2: tens of ms per page on A100, <0.5 s on
L4. NIM/vLLM both give continuous batching; NIM VLM documents
`nvext.guided_json` structured output
([docs](https://docs.nvidia.com/nim/vision-language-models/1.1.1/structured-generation.html)).

## 4. Fit for Label Check (PLAN-us-stack.md)

1. **PR4's pre-M2 spike is now largely answered**: Nemotron Nano 2 VL is
   verifiably deployable on Azure AI Foundry today (catalog entry + NIM on
   managed compute + NVAIE marketplace fee), and the fee-free variant
   (vLLM on an Azure GPU VM) is confirmed viable. Remaining spike work is
   just pricing the chosen SKU and measuring our real per-panel latency.
2. **Escalation-model ranking for the plan (Approach A):**
   **Nano 2 VL 12B (FP8)** is the sweet spot — best license (no Llama
   strings, no NVAIE if vLLM-served), 24 GB-card economics, 128K context,
   guided-JSON, and OCRBench v2 62.0. **Nano Omni 30B** is the accuracy
   ceiling (+3.8 OCRBench v2) at ~2x the VRAM and with the heaviest
   Qwen-in-post-training disclosure — worth it only if M1 eval shows the
   12B missing fields the 30B catches. **8B VL (AWQ 4.8 GB)** is the
   budget/edge option.
3. **A new Approach C′ candidate**: the reviewed plan's local-only
   alternative (Tesseract + Granite-Docling) assumed CPU. If a modest GPU
   (L4/T4-class) is allowed, **Tesseract L1 + nemotron-ocr-v2 L1.5
   (~2-3 GB VRAM, <0.5 s/page, clean lineage, beats PaddleOCR on NVIDIA's
   benchmarks)** becomes a compelling local-only US stack — stronger than
   Granite-Docling for photographed text, and it can share a card with a
   quantized VLM. Caveat: NVIDIA's anti-Paddle numbers are self-reported
   document-corpus benchmarks; **our M1 eval on the label corpora is still
   the decision data** — scene-text/label performance is unproven there.
4. **Strict-lineage tension to surface at any adoption gate**: the
   best-accuracy NVIDIA VLMs carry Qwen-assisted training disclosures. If
   "moving completely off PRC ecosystems" means training-chain purity,
   escalate to nemotron-ocr-v2/Parse (clean) + 8B VL (clean weights, Llama
   terms) — or accept the documented asterisk on the 12B/30B and note it
   in the SBOM. This is a policy call, not a technical one.
5. **License inventory additions if adopted**: NVIDIA (Nemotron) Open Model
   License (guardrail-termination clause noted), plus Llama 3.1 Community
   License if the 8B is used.

## Caveats

- Benchmark numbers mix official-leaderboard (OCRBench v2 2026.06) and
  self-reported model-card figures — noted inline; "KDL Frontier" (#1)
  remains an unverified org.
- nemotron-ocr's superiority claims vs PaddleOCR/EasyOCR are NVIDIA's own
  benchmarks on document corpora; no independent olmOCR-bench entry exists
  for it as of Aug 2026.
- Latency figures marked [E] in the underlying research are estimates, not
  measurements — measure on the target SKU during the M2 spike.
- Licensing/pricing (NVAIE rates, Azure marketplace terms, Developer
  Program limits) move quickly — re-verify before procurement.
