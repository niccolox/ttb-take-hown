# AI Supply-Chain Risk: OCR, VLM, and LLM for a Treasury-Facing Tool

Research date: 2026-08-02. Scope: supply-chain risk of the current PaddleOCR
stack and a US-domestic-first map of alternatives across OCR engines,
vision-language models (VLMs), text LLMs, and the vLLM inference engine.
Compiled from three parallel research passes plus a local dependency audit;
every load-bearing claim carries a source. Re-verify 2026-dated claims against
primary vendor pages before citing in anything official.

---

## TL;DR

1. **Our current OCR stack is PRC-origin end to end**: PaddleOCR/PaddlePaddle
   are Baidu-controlled, models download from Baidu Cloud (Beijing region) at
   Docker build time, and the install footprint includes two PRC model-hub
   SDKs we never call. The project's existing mitigations (pins, baked models,
   verified `--network none` boot) neutralize the *live* attack vectors, but
   provenance, governance, and policy-optics risk remain.
2. **No federal rule bars this today — but every 2025-2026 policy signal
   points the same direction** (prefer US-developed AI; pending
   foreign-adversary AI blocklist; Treasury's own Dec 2024 supply-chain breach
   by a PRC actor). For a TTB-facing tool, PRC-origin ML is a likely review
   flashpoint even where it is technically permitted.
3. **A US-domestic stack is viable in 2026 without a large accuracy
   sacrifice** — but watch model lineage, not just the releasing org: most
   modern "US" OCR VLMs (olmOCR-2, Chandra, Nanonets) are fine-tunes of
   Alibaba's Qwen-VL. The clean-lineage US shortlist is IBM Granite
   (Docling/Vision), Microsoft TrOCR/Florence-2/Phi-4, Tesseract, NVIDIA
   Nemotron VL, and AI2's Olmo/Molmo-O line.
4. **vLLM (the inference engine) is a clean US choice** — Berkeley origin,
   PyTorch Foundation (Linux Foundation) governance, Apache 2.0, Red Hat/IBM
   stewardship. Pin ≥ 0.18.0 (CVE-2026-27893 RCE via hardcoded
   `trust_remote_code`).

---

## 1. Current stack audit (this repo, verified locally)

Direct pins: `paddleocr==3.2.0`, `paddlepaddle==3.2.2` (79 packages total in
the uv venv).

**Findings:**

- **Transitive PRC hub SDKs**: `paddleocr → paddlex 3.2.1` installs
  `aistudio-sdk` (Baidu AI Studio client) and `modelscope` (Alibaba model-hub
  client). Our code never calls them, but they sit on the install footprint —
  attack surface and SBOM noise.
- **Hardcoded endpoints in installed code**:
  `paddle-model-ecology.bj.bcebos.com` (Baidu Object Storage, Beijing region —
  models/fonts/assets), `qianfan.baidubce.com/v2` (Baidu's Qianfan LLM API
  client), `paddlepaddle.org.cn`.
- **Startup network behavior confirmed upstream**: PaddleOCR issue #16620
  (filed against exactly our 3.2.0/3.2.x pins) documents that the pipeline
  contacts Hugging Face, ModelScope, AIStudio, and BOS at initialization
  *before* checking local cache, and fails offline unless model dirs are
  pinned explicitly — which is precisely what `api/extractor.py` does
  (explicit `model_dir`s + warm-time assertion).
- **Build-time trust gap**: the Dockerfile bakes models by downloading once
  from Baidu's CDN during `docker build`. Runtime egress is blocked (verified
  `--network none` boot), but **the downloaded weights are not
  checksum-pinned** — a compromised CDN response at build time would be baked
  silently. This is the top actionable gap.
- Existing mitigations already shipped: exact version pins, baked models with
  warm-time dir assertions (a pin bump can't silently re-enable egress),
  no-egress runtime verification, loopback-only compose.

## 2. PaddleOCR / PaddlePaddle risk profile

**Provenance and governance.** PaddlePaddle was developed at Baidu and
open-sourced in 2016 as "China's first independent R&D deep learning
platform"; Baidu remains the controlling maintainer, with hardware partners
including Huawei, Arm China, Cambricon
([viso.ai](https://viso.ai/deep-learning/paddlepaddle/),
[eWeek 2016](https://www.eweek.com/development/baidu-open-sources-paddlepaddle-deep-learning-platform/)).
PaddleOCR lives in the Baidu-controlled GitHub org (Apache 2.0, ~87k stars,
release 3.7.0 June 2026) with **no SECURITY.md and no neutral governance** —
no foundation, no steering committee independent of Baidu
([repo](https://github.com/PaddlePaddle/PaddleOCR), fetched 2026-08-02).
Newer PaddleOCR-VL models integrate with Baidu's ERNIE stack.

**Model hosting.** Official weights are hosted on Baidu Object Storage
(`*.bj.bcebos.com`, Beijing region) with Hugging Face as the 3.x default
download source (`PADDLE_PDX_MODEL_SOURCE`; AIStudio and ModelScope also
supported)
([PaddleOCR docs](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/module_usage/text_detection.html)).

**Telemetry.** No deliberate analytics/phone-home endpoint was found in
current versions; observed network behavior is model-resolution traffic at
startup (see §1). But no privacy policy, telemetry documentation, or formal
third-party traffic audit exists — a third-party packager patches out the
cloud-storage domains before import as a mitigation
([ocr_tools](https://codeberg.org/entai2965/ocr_tools)). The absence of an
audit is itself a finding.

**CVEs.** A 2023-2024 wave (huntr/Protect AI bounty reporting) hit
PaddlePaddle ≤ 2.6.0: critical RCE CVE-2024-0917 (CVSS 9.4), command
injection CVE-2023-52310/-52314 (9.8), arbitrary file read CVE-2024-1603, and
~11 moderate memory-corruption bugs
([GHSA](https://github.com/advisories?query=paddlepaddle)). **All published
framework CVEs predate our 3.2.2 pin.** 2025-2026 is nearly silent (only
CVE-2026-10800 in FastDeploy, a separate toolkit we don't use) — more
plausibly reduced researcher attention than a hardened codebase, given no
public security program. Oligo also demonstrated a no-CVE pickle-RCE pattern
in Paddle Serving (not in our stack)
([Oligo](https://www.oligo.security/blog/oligo-adr-in-action-paddlepaddle-shadow-vulnerability)).
Note our baked `.pdmodel`/`.pdiparams` files are protobuf+tensors, not Python
pickles — the classic deserialization-RCE vector doesn't apply to the baked
models themselves.

## 3. US federal policy landscape (mid-2026)

- **Enacted/near-enacted bans target hosted PRC services, not self-hosted
  libraries — so far.** DeepSeek is banned on government devices at Commerce,
  Navy, and several states; H.R.1121 would mandate removal government-wide
  ([Congress](https://www.congress.gov/bill/119th-congress/house-bill/1121)).
  The **No Adversarial AI Act** (H.R.4142/S.2177, introduced June 2025, not
  enacted as of mid-2026) would bar federal acquisition/use of AI "produced or
  developed by a foreign adversary entity" via a Federal Acquisition Security
  Council blocklist — a mechanism that could capture Baidu-produced AI
  ([Akin](https://www.akingump.com/en/insights/ai-law-and-regulation-tracker/us-lawmakers-introduce-no-adversarial-ai-act)).
- **ICTS (EO 13873)** is the most plausible existing authority to reach
  PRC-origin AI software broadly: Commerce's final rule formalizing the ICTS
  program took effect Feb 2025, and the first class-wide rule (connected
  vehicles, Jan 2025) already bans PRC-nexus *software*
  ([BIS](https://www.bis.gov/press-release/commerce-issues-final-rule-formalize-icts-program)).
  Section 889 does not currently reach Baidu.
- **Software attestation rules changed in 2026**: OMB **M-26-05 (Jan 2026)
  rescinded M-22-18/M-23-16** — blanket SSDF attestation collection is gone,
  replaced by agency-led, risk-based review
  ([Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2026/02/omb-rescinds-biden-era-software-security-memoranda)).
  Practical effect for us: the question becomes "can you survive a Treasury
  risk assessment," where a clean SBOM, pinned hashes, and the air-gapped
  design are the strongest answers.
- **Affirmative US-preference guidance**: OMB M-25-21/M-25-22 (Apr 2025) tell
  agencies to prefer AI developed and produced in the United States;
  **America's AI Action Plan** (July 2025) frames US open-weight models as the
  counter to Chinese alternatives and directs NIST to build "CCP alignment"
  evaluations for Chinese models
  ([WH PDF](https://www.whitehouse.gov/wp-content/uploads/2025/07/Americas-AI-Action-Plan.pdf)).
  The ATOM Project (Aug 2025) is the ecosystem push to rebuild US open-model
  leadership ([atomproject.ai](https://www.atomproject.ai/)).
- **Treasury context**: Dec 2024, a PRC state actor breached Treasury
  Departmental Offices via BeyondTrust Remote Support (stolen API key +
  CVE-2024-12356/-12686; ~100 workstations including OFAC-adjacent offices) —
  a third-party-software supply-chain compromise by a PRC actor, i.e. exactly
  the risk class a Baidu-origin OCR stack presents
  ([wiki](https://en.wikipedia.org/wiki/2024_United_States_Department_of_the_Treasury_hack)).
  No published federal Treasury policy on PRC AI models was found.

## 4. General ML supply-chain attack surface (why the paranoia is earned)

- **Malicious model weights**: ~100 malicious pickle models found on Hugging
  Face (JFrog, Mar 2024); the nullifAI technique (Feb 2025) evaded HF's
  Picklescan while still executing on load; JFrog disclosed three Picklescan
  bypasses, each CVSS 9.3, in Dec 2025
  ([ReversingLabs](https://www.reversinglabs.com/blog/rl-identifies-malware-ml-model-hosted-on-hugging-face)).
- **PyPI release compromise of a flagship vision package**: ultralytics (YOLO)
  shipped a cryptominer in four releases over Dec 4-7, 2024 via GitHub Actions
  branch-name injection + a stolen PyPI token
  ([Wiz](https://www.wiz.io/blog/ultralytics-ai-library-hacked-via-github-for-cryptomining)).
  An 86k-star package shipped malware for hours; exact-version pinning is what
  bounds this window.
- **Dependency confusion**: torchtriton (Dec 2022) poisoned PyTorch-nightly
  resolution and exfiltrated system data — the canonical case for hash-locked
  installs in ML stacks.

## 5. US-domestic OCR alternatives

Fit context: photographed alcohol labels — stylized fonts, curved text, small
print (government warning). "Clean lineage" = no PRC base model anywhere in
the training ancestry.

| Candidate | Control | License (code / weights) | Clean lineage | CPU | Scene/stylized text | Health mid-2026 |
|---|---|---|---|---|---|---|
| **Tesseract 5.5** | US-origin (HP); int'l community (not Google) | Apache / Apache | Yes | Yes | **Weak** | Alive, slow |
| **TrOCR** (Microsoft) | US | MIT / MIT (incl. scene-text ckpts, curved-text CUTE80) | Yes | Yes (~330M) | Good (recognition-only; needs detector) | Frozen ~2022 |
| **Florence-2** (Microsoft) | US | MIT / MIT | Yes | Marginal (0.23-0.77B) | Good in-the-wild | Frozen 2024; needs `trust_remote_code` |
| **Granite-Docling 258M** (IBM) | US | Apache / Apache | Yes (SigLIP2 + Granite) | **Yes** | Document-tuned; needs eval on photos | Active (GA Jan 2026) |
| **olmOCR-2 7B** (AI2) | US non-profit | Apache / Apache | **No — Qwen2.5-VL base** | Barely (GGUF) | Strong on messy docs | Very active |
| **Chandra 2** (Datalab) | US startup | Apache / RAIL-M $2M rev cap + API non-compete | **No — Qwen3-VL base** | No (GPU) | Strong; SOTA olmOCR-bench 85.9% | Very active |
| **Surya/Marker** (Datalab) | US startup | Apache / RAIL-M $5M cap | Yes | Slow | **Explicitly not for scene text** (README) | Very active |
| **Azure Document Intelligence** (Microsoft) | US | proprietary | n/a | GPU rec. | Good (Read + handwriting) | Active; **disconnected/air-gapped containers exist**; use v4.0 (v2.1 EOL 8/31/2026) |
| **Apple Vision framework** | US | proprietary, on-device | n/a (black box) | Apple Silicon | **Very good on photos** (Live Text) | Active; macOS/iOS only |
| docTR / OnnxTR | France (Mindee) → community | Apache / Apache | Yes | Yes | Moderate, rotation-robust | Active |
| EasyOCR | Thailand (Jaided AI) | Apache / Apache | Yes | Yes | Good (CRAFT) | **Stagnant** (last release Sep 2024) |
| Mistral OCR 4 | France | proprietary | n/a | No | Strong doc AI | Active; self-host enterprise-only |
| AWS Textract | US | n/a | n/a | n/a | Good | **Cloud-only, no on-prem** |
| Google Vision/Doc AI | US | n/a | n/a | n/a | Very good | **On-prem path shut down Sep 2025** |
| RapidOCR | **PRC community repack of Baidu weights** | Apache | No | Yes | Same as Paddle | Not an alternative |

**Negative findings that matter:**
- **No one distributes provenance-attested/audited ONNX conversions** of OCR
  weights — community HF repacks are unaudited; RapidOCR keeps Baidu weights
  and PRC maintainership. There is no "laundered Paddle" escape hatch.
- **The Qwen-base caveat is pervasive**: olmOCR-2, Chandra, and Nanonets-OCR2
  are all Alibaba Qwen-VL fine-tunes. US org + Apache license ≠ US lineage.
- Google and AWS have exited/never had the on-prem OCR business; **Azure is
  the only hyperscaler with genuinely air-gappable OCR containers**.

**Fit assessment**: the strict clean-lineage + offline + CPU shortlist for
this project is **Granite-Docling 258M** (needs eval on label photos — it's
document-conversion-tuned), **TrOCR/Florence-2** (capable but frozen
artifacts), **Tesseract** (fine only as a cheap second-pass on the deskewed
warning block), and **Azure DI disconnected containers** (proprietary,
commitment-tier contract). Best raw accuracy on hard label photos among local
options is VLM-class (Chandra 2, olmOCR-2) — but both carry Qwen lineage and
GPU requirements.

## 6. VLM landscape (for a future hard-photo assist)

US-controlled, by fit:

- **IBM Granite Vision** (3.2/3.3 2B; Granite 4.0 3B Vision, Apr 2026) —
  Apache 2.0, training-data transparency, purpose-built for enterprise
  document extraction. Best license+size+purpose fit for label reading
  ([IBM](https://www.ibm.com/granite/docs/models/vision)).
- **NVIDIA Nemotron VL line** — Llama-Nemotron-Nano-VL-8B topped OCRBench at
  release; **Nemotron 3 Nano Omni 30B is #2 on OCRBench v2 (2026.06), the top
  verified US open-weight entry**. Nemotron Open Model License allows
  commercial use but has a guardrail-bypass termination clause
  ([NVIDIA](https://developer.nvidia.com/blog/new-nvidia-llama-nemotron-nano-vision-language-model-tops-ocr-benchmark-for-accuracy)).
- **Microsoft Phi-4-multimodal** (5.6B) — MIT, strong small-model doc VQA.
- **AI2 Molmo 2** — Apache 2.0, but **the 8B/4B sizes use Qwen3 backbones**;
  only Molmo 2-O 7B is fully US-lineage (Olmo backbone)
  ([AI2](https://allenai.org/blog/molmo2)).
- **Meta Llama 4 vision** — community license (not OSI; 700M-MAU cap, EU
  exclusions); mixed reception.
- **Google Gemma 3/4 vision** — Gemma 4 (2026) moved to Apache 2.0.

PRC flag tier (dominant on benchmarks through 2025): Qwen2.5/3-VL (Alibaba),
InternVL3.x (Shanghai AI Lab, state-backed), DeepSeek-VL/-OCR, GLM-4V
(Zhipu), MiniCPM-V. As of the OCRBench v2 2026.06 English leaderboard, the
top tier is still majority PRC-origin, **but NVIDIA Nemotron sits at/near the
top and Granite/Phi cover the small-model niche — a US-only stack no longer
costs much accuracy on document tasks**
([leaderboard](https://99franklin.github.io/ocrbench_v2/)).

## 7. LLM landscape

US open-weight: **gpt-oss-120b/20b** (OpenAI, Aug 2025, Apache 2.0 — first
OpenAI open weights since GPT-2), **Olmo 3/3.1** (AI2 — fully open: weights +
data + code; maximum audit transparency, relevant if Treasury wants provable
provenance), **Llama** (Meta, community license), **Gemma 4** (Google, Apache
2.0), **Phi-4** (Microsoft, MIT), **Granite** (IBM, Apache 2.0 + data
disclosure), **Nemotron** (NVIDIA). France: Mistral (Small line Apache 2.0).
PRC flag tier: Qwen, DeepSeek V4, Kimi K2.6, GLM-5.x — consistently at or
near open-weight SOTA; capability-gap estimates for US open models range from
"3-7 months behind" (Epoch) to wider (CAISI).

US commercial APIs with a federal path (if the no-cloud premise is ever
relaxed for a Treasury deployment):
- **Anthropic Claude via Amazon Bedrock in AWS GovCloud: FedRAMP High + DoD
  IL4/IL5** (May 2025) — the most mature authorized route
  ([AWS](https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-bedrock-models-fedramp-high-dod-il-4-5-govcloud/)).
- **Azure OpenAI in Azure Government: FedRAMP High**; ChatGPT Gov deployable
  in agency tenants; OpenAI SaaS itself at FedRAMP Moderate (High in
  progress).
- **Google Gemini/Vertex: FedRAMP High**; "Gemini for Government" OneGov deal
  ($0.47/agency through 2026).

## 8. vLLM (the inference engine)

Origin UC Berkeley (PagedAttention team); since May 2025 a PyTorch
Foundation-hosted project (Linux Foundation umbrella); Apache 2.0; dominant
commercial steward is Red Hat/IBM (Neural Magic acquisition), with NVIDIA,
Meta, AMD, Intel, Google, AWS contributing
([PyTorch Foundation](https://pytorch.org/blog/pytorch-foundation-welcomes-vllm/)).
**US-domestic on every axis.** Supply-chain notes:

- **Pin vLLM ≥ 0.18.0**: CVE-2026-27893 — vLLM hardcoded
  `trust_remote_code=True` for certain architectures, bypassing user settings
  and enabling RCE via malicious HF model repos
  ([advisory](https://raxe.ai/labs/advisories/RAXE-2026-044)).
- The engine's risk is the **model-ingestion path, not the engine**: vendor
  weights into an internal store (no live Hub pulls), safetensors only,
  `trust_remote_code=False`, pinned digests, prefer natively-supported
  architectures, and treat `vllm.general_plugins` entry points as arbitrary
  code (allowlist).

## 9. Recommendations (ranked)

1. **Close the build-time gap now (S)**: checksum-pin the baked model weights
   — record SHA-256 of each model dir's files at a known-good build and
   assert them in the Dockerfile after download (and in the extractor's warm
   assertion). Converts "trust Baidu's CDN at every build" into "trust it
   once, verify forever."
2. **Hash-lock the Python install (S)**: generate a fully pinned
   `requirements.lock` with hashes (`uv pip compile --generate-hashes`) so a
   PyPI release compromise (ultralytics-style) or dependency confusion cannot
   ship code silently.
3. **Produce an SBOM (S)**: CycloneDX/SPDX for the image, with the PRC-origin
   components explicitly annotated (paddleocr, paddlepaddle, paddlex,
   aistudio-sdk, modelscope) and the mitigations documented. Under M-26-05's
   risk-based regime this is the artifact a Treasury review will ask for.
4. **Investigate excluding the unused PRC hub SDKs (S-M)**: `aistudio-sdk`
   and `modelscope` are paddlex transitive deps our code never imports. Test
   whether install-time exclusion (uv override/no-deps install) keeps the
   pipeline working; smaller footprint, cleaner SBOM.
5. **Run a swap-feasibility eval behind the Extractor interface (M)**: the
   architecture already isolates OCR behind `api/extractor.py`. Benchmark
   **Granite-Docling 258M** (clean US lineage, Apache, CPU-class) and
   **Tesseract-as-second-pass** on the existing eval corpora
   (`api/eval/colacloud/`, 80+ labels with ground truth) against the Paddle
   baseline. This produces the decision-grade number: what accuracy do we
   actually give up for a clean-lineage US stack today?
6. **If/when a VLM assist lands (per TODOS "Optional VLM assist")**: default
   candidates in order — Granite Vision (license+size+purpose), Nemotron VL
   (accuracy), Phi-4-multimodal (MIT, small). Avoid Qwen-lineage fine-tunes
   (olmOCR, Chandra, Nanonets, Molmo 2 non-O) if clean lineage is a
   requirement. Serve with vLLM ≥ 0.18.0, vendored safetensors,
   `trust_remote_code=False`.
7. **Positioning for the take-home writeup**: the current stack is defensible
   *as shipped* (pinned, baked, air-gapped, all CVEs predate the pin) — say
   so, cite the mitigations, and present the migration path above as the
   roadmap. "We know what's in the box, we bolted the door, and we know what
   we'd swap to" is a stronger answer than either ignoring the Baidu question
   or a rushed engine swap.

## Caveats

- 2026-dated items (OCRBench v2 2026.06 ordering, "KDL Frontier" #1 entry,
  Claude for Government desktop beta, Gemma 4 licensing, Chandra 2/olmOCR-2
  release details) rest partly on secondary sources; re-verify before formal
  citation.
- No formal third-party traffic audit of PaddleOCR exists; our `--network
  none` verification covers runtime, not build.
- Policy is moving: track the No Adversarial AI Act (H.R.4142/S.2177) and any
  FASC foreign-adversary-AI listing — either would change "defensible" to
  "scheduled for removal" for Baidu-origin components.
