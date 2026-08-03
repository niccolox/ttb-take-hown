# Nemotron 3 Nano Omni on Azure Foundry — VLM Integration + DevSecOps/PRC Audit (2026-08-03)

Sources (fetched 2026-08-03): HF × Microsoft deployment guide
(deploy-nemotron-3-nano-omni), NVIDIA developer blog + HF model cards for
`nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-{BF16,FP8,NVFP4}`, NVIDIA
NIM API reference, community technical reviews. Companions:
docs/plans/azure-enrichment-layers.md (E1 shipped), docs/enable-azure-vlm.md,
docs/research/azure-frontier-models.md (placement standard),
docs/research/ai-supply-chain-risk.md (risk framework).

## What it is

`Nemotron-3-Nano-Omni-30B-A3B`: open-weights multimodal model — video,
audio, image, text in; text out. NVIDIA's own **Mamba2-Transformer hybrid
MoE** backbone (31B total, ~3B active), C-RADIOv4-H vision encoder,
Parakeet-TDT audio encoder. Natively does OCR, GUI understanding, and
speech transcription — i.e., it overlaps BOTH our J3 assist role and,
potentially, a future third-engine re-reader.

## Integration fit: works with E1 as shipped

The guide deploys it as an **Azure ML Managed Online Endpoint** (Foundry
classic) from the HuggingFace registry onto a dedicated
`Standard_NC24ads_A100_v4` (1×A100), served **OpenAI-compatible** at
`/v1/chat/completions` with structured content arrays and key auth.
That is exactly the surface our E1 azure dialect emits:

```bash
LABELCHECK_VLM_PROVIDER=azure
AZURE_VLM_ENDPOINT=https://<endpoint>.<region>.inference.ml.azure.com/v1/chat/completions
AZURE_VLM_KEY=<AML endpoint primary key>       # sent as Bearer — AML accepts it
AZURE_VLM_MODEL=nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16
```

Two small operational notes (candidate **E1b**, ~30 min):
1. **Deployment routing header.** AML routes by traffic weights; with one
   deployment at 100% no header is needed. Supporting an optional
   `AZURE_VLM_DEPLOYMENT` → `azureml-model-deployment` header makes
   blue/green endpoint work (two deployments) addressable.
2. **Timeout.** The guide raises AML's request timeout to 180 s for long
   media; our client holds a 30 s timeout, which is right for crops (small
   JPEGs, image-only) but a cold or queued endpoint can exceed it — the
   breaker handles that correctly (silent no-op, cooloff), just expect
   suggestion gaps under cold starts rather than errors.

## Why this option is strategically interesting

This is not another hosted-model API: it is **open weights running on
compute in OUR tenancy**. Against the model-placement standard that
changes the calculus:

| Option | Model access | Data plane | Placement tier |
|---|---|---|---|
| NVIDIA hosted NIM (today's nvidia provider) | API | third-party (NVIDIA) | goldens only |
| Frontier MaaS (GPT-5.x / Claude 4.6 via Foundry) | API | provider-operated in FedRAMP High boundary | goldens only (per standard) |
| **Nemotron Omni on AML managed endpoint** | open weights | **our subscription, dedicated instance** | strongest story: no model-provider data plane at all |
| Same weights on-prem beside the OCR sidecar | open weights | our hardware | equivalent; already the N5 production sketch |

An in-tenant open-weights endpoint (private-endpoint'd, VNet-isolated) is
the only hosted-VLM shape with a credible path to touching real
pre-approval imagery someday — the data never meets a model vendor. That
clearance still requires the written placement-standard update; nothing
is cleared today.

## DevSecOps audit of the deployment recipe

**D1 — Mutable model reference (the guide's own example). MEDIUM.** The
deployment pins `azureml://registries/HuggingFace/models/...`
**`/labels/latest`** — the registry-side equivalent of a mutable image
tag, the exact class we just closed with digest pins. Fix: resolve and
pin a specific model **version** from the registry (and record the HF
commit hash + weight file hashes beside it — extend `models.sha256`
thinking to VLM weights).

**D2 — Public scoring URI by default. MEDIUM.** Managed endpoints expose
a public regional URI with key auth. For goldens-only dev that is
acceptable; anything beyond requires the private-endpoint/VNet
configuration and key rotation via AML (both supported, neither in the
guide). Add to the enable doc when an endpoint is stood up.

**D3 — Key handling. LOW (posture exists).** Primary key via
`get_keys()` — lands in Key Vault per our standard, never in compose;
AML supports Entra-token auth on scoring as the stronger alternative
(managed identity instead of static key) — prefer it at stage+.

**D4 — Cost/idle. LOW.** Dedicated 1×A100 bills while deployed (the
guide's own teardown section is the control). For J3's duty cycle
(3 crops per amber label), NIM/serverless is cheaper for dev; the AML
shape earns its cost only when tenancy isolation is the point.

**D5 — Ops fit. GOOD.** OpenAI-compatible surface = zero new client
code; AML gives autoscale, logs to Log Analytics, and slots into the
CI/CD plan's Bicep/IaC posture. The 10-assets-per-modality limit is
irrelevant at one crop per call.

## PRC supply-chain audit (the honest read)

Applying the ai-supply-chain-risk framework's distinction — *what code
executes, whose weights, what shaped the weights*:

- **Code that executes: NVIDIA/US.** Serving stack is vLLM-class on
  AML; no PRC-origin code in the path (unlike paddle, which is PRC code
  executing in-process and is triple-locked for exactly that reason).
- **Architecture + weights: NVIDIA.** Nemotron-H hybrid Mamba2/MoE
  backbone, NVIDIA-trained; C-RADIOv4 and Parakeet encoders are NVIDIA's
  own. The `30B-A3B` naming resembles Qwen3's MoE convention but the
  architecture is not a Qwen fork.
- **Training-data provenance: MIXED — disclosed.** The model card lists
  PRC-origin models among its improvement/distillation teachers
  (Qwen3-VL-30B-A3B-Instruct, Qwen3.5-122B/397B, Qwen2.5-VL-72B) beside
  gpt-oss-120b. So: US-built model, partly taught on synthetic data from
  PRC-origin models. Risk class = **training-data influence**
  (distillation-borne behaviors/alignment artifacts), NOT code execution
  and NOT weight custody. Materially weaker than the paddle risk we
  already carry and mitigate; not zero, and M-26-05-style reviews will
  ask, so it goes in the record:
  - SBOM/model annotation: add a `labelcheck:origin-risk` property for
    any deployed VLM weights noting the disclosed Qwen-teacher lineage
    (same mechanism as the paddle annotations).
  - Behavioral mitigation is ALREADY structural: suggestion-only (no
    status mutation), crops-only, escaped rendering, and the planned
    `trap_prompt_injection` golden (plan E2) — a distillation-borne
    quirk cannot alter a verdict by construction.
  - Compare: Nemotron **Nano VL 8B** (today's nvidia-provider model) is
    Llama-3.1-based — cleaner data-lineage story at lower capability;
    keeping it available via the provider switch is itself a mitigation.

**Verdict:** viable and strategically attractive as the in-tenant VLM;
adopt with (a) registry-version pinning + weight hashes (D1), (b)
private endpoint + Entra auth beyond dev (D2/D3), (c) the lineage
disclosure annotated in the SBOM, and (d) E2's injection trap landed
before any real-data conversation. The provider switch shipped in E1
means trying it is a four-line `.env` change against a deployed
endpoint — no further code required (E1b header support optional).
