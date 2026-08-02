# Deploying Nemotron OCR v2 (NIM) on Azure Virginia — Runbook

Research date: 2026-08-02. Scope: step-by-step deployment of the NVIDIA
Image OCR NIM (`nemotron-ocr-v2`) on Azure GPU infrastructure in Virginia —
commercial (East US / East US 2) and Azure Government (usgovvirginia).
Premise confirmed by research: **the container ships only from NVIDIA's NGC
registry (`nvcr.io`), not Microsoft Container Registry, and is absent from
the Azure AI Foundry catalog** — so every path below starts with an NGC
pull. Verified against docs.nvidia.com, NGC catalog pages, Microsoft Learn,
and live Azure Retail Prices API queries; explicitly-unverified items are
flagged at the end. Companion docs: `nvidia-ocr-lineage-azure.md`,
`nvidia-open-ocr.md`.

---

## 0. The container, in facts

| Item | Value |
|---|---|
| Image (current) | `nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.0` (~962 MB; NGC page updated 2026-07-16) |
| Image (legacy v1) | `nvcr.io/nim/nvidia/nemoretriever-ocr-v1:1.1.0` |
| Port | 8000 (HTTP only; no gRPC documented) |
| API | **`POST /v1/ocr`** (breaking change from v1's `/v1/infer`); base64 data-URI images; `merge_levels`: word\|sentence\|paragraph; response = `text_detections[]` with text+confidence and **normalized [0,1] bounding boxes** |
| Health | `GET /v1/health/ready`, `GET /v1/health/live` |
| VRAM | English 1.6-2.1 GiB; multilingual (default) 2.7-3.2 GiB FP16 |
| GPUs validated | A100, **A10G**, L4, L40S, H100/H200, B200, GB200, RTX PRO 6000. **T4 NOT supported** (Turing). Multi-GPU not supported in 2.0.0 |
| Azure nuance | Azure sells **A10** (not A10G) — same GA102 Ampere silicon, expected to work but **not an explicitly validated SKU**; fractional A10 sizes run vGPU/GRID profiles the matrix doesn't validate |
| Entitlement | Pullable with a **free NVIDIA Developer Program NGC key** for dev/test; **production requires NVIDIA AI Enterprise**; weights under NVIDIA Open Model License |
| Tuning knobs | `NIM_PERFORMANCE_MODE` (0=latency, 1=throughput), `NIM_PIPELINE_MAX_BATCH_SIZE` (1/16), `NIM_ENGINE_COUNT` (1/2), `NIM_SERVER_MAX_WAIT_MS` |

Docs: [getting started](https://docs.nvidia.com/nim/ingestion/image-ocr/latest/getting-started.html) ·
[NGC v2 page](https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/nemotron-ocr-v2) ·
API/support-matrix/configuration pages under the same doc tree.

## 1. Prerequisites (once)

1. **NGC API key**: generate at https://org.ngc.nvidia.com/setup/api-keys
   (service: NGC Catalog). Accept any click-through license on the NGC
   container page.
2. **Registry login** (the username is the literal string `$oauthtoken`):
   ```bash
   echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
   ```
3. **Licensing check**: free developer key covers development/testing;
   before production, procure NVAIE (Azure Marketplace private offer for
   commercial — MACC-eligible; for Gov, engage NVIDIA sales — no Gov
   marketplace offer was verifiable).

## 2. Path A — Azure GPU VM (the baseline; works commercial AND Gov)

### 2.1 Pick the SKU (Virginia pricing, live-queried 2026-08-02)

| SKU | GPU | eastus/eastus2 PAYG | Spot | usgovvirginia PAYG | Spot |
|---|---|---|---|---|---|
| **NV36ads_A10_v5** (full A10 24 GB) | 1× A10 | $3.20/hr | **$0.591/hr** | $4.00/hr | **$0.739/hr** |
| NV12ads_A10_v5 (⅓ A10, 8 GB vGPU) | fractional | — | — | $1.135/hr | $0.210/hr |
| NC24ads_A100_v4 (commercial only as single-GPU) | 1× A100 80GB | $3.673/hr | — | not sold single-GPU in Gov | — |

- Lowest-risk: **NV36ads (full A10)** — closest to the validated A10G, no
  vGPU-profile question. The model needs <3.2 GiB, so the ⅓-A10 NV12ads is
  ample by VRAM — but fractional = vGPU/GRID, unvalidated; treat as the
  budget option, not the safe one.
- Spot is dramatic here (~82% off) and reasonable for a stateless OCR
  service with `--eviction-policy Deallocate` + a restart script.

### 2.2 Create the VM

```bash
# For Gov first: az cloud set --name AzureUSGovernment && az login
az vm create -g rg-ocr -n vm-ocr \
  --location eastus2 \                     # or usgovvirginia
  --size Standard_NV36ads_A10_v5 \
  --image Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest \
  --admin-username azureuser --generate-ssh-keys \
  --priority Spot --eviction-policy Deallocate   # optional
```
NSG: open 22 for admin only. **Do not expose 8000 publicly — the NIM has no
built-in auth**; front it with a private endpoint/ILB or keep it on the
VNet for the FastAPI caller.

### 2.3 Install the GPU driver — with the known A10 gotcha

The NVIDIA GPU Driver Extension currently installs **GRID 17.5, which has a
documented CUDA-breaking bug on the A10 series** (extension page, updated
2026-06-24). Pin GRID 16.5:

```bash
az vm extension set -g rg-ocr --vm-name vm-ocr \
  --name NvidiaGpuDriverLinux --publisher Microsoft.HpcCompute \
  --settings "{'driverVersion':'535.161'}"
```

Other constraints: Ubuntu 22.04/24.04; Secure Boot unsupported by the
extension; kernel 6.11 has GRID install issues (use 6.8). Alternative on
commercial Azure: the **NVIDIA GPU-Optimized VMI** from the Marketplace
(offer `ngc_azure_17_11`; there is a dedicated vGPU-driver variant
`nvidia-gpu-optimized-vmi-a10` for fractional sizes) — preinstalls driver,
Docker, and nvidia-container-toolkit. **Assume the VMI is NOT in the Gov
marketplace** (unverified) — in Gov, use the stock-Ubuntu + extension path.

### 2.4 Docker + container toolkit, then run

```bash
# on the VM: install docker-ce + nvidia-container-toolkit (standard NVIDIA docs)
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
export LOCAL_NIM_CACHE=~/.cache/nim && mkdir -p "$LOCAL_NIM_CACHE"/{cache,weights}

docker run -d --restart unless-stopped --name nemotron-ocr \
  --runtime=nvidia --gpus '"device=0"' --shm-size=16GB \
  -e NGC_API_KEY \
  -e NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc \
  -e NIM_PERFORMANCE_MODE=0 \
  -v "$LOCAL_NIM_CACHE/cache:/opt/cache" \
  -v "$LOCAL_NIM_CACHE/weights:/model" \
  -u $(id -u) -p 8000:8000 \
  nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.0
```
(The docs' verbatim command uses `-it --rm`; above is the service-ified
variant. First start downloads weights from NGC into the mounted volume;
`NIM_ENGINE_MODEL_DOWNLOAD_ONLY=1` pre-stages weights without serving.)

### 2.5 Verify

```bash
curl http://localhost:8000/v1/health/ready
# {"object":"health.response","message":"ready","ready":true}

curl -X POST http://localhost:8000/v1/ocr \
  -H 'Content-Type: application/json' \
  -d '{"input":[{"type":"image_url","url":"data:image/png;base64,'"$(base64 -w0 label.png)"'"}],
       "merge_levels":["word"]}'
# → data[0].text_detections[]: {text_prediction:{text, confidence},
#    bounding_box: {points normalized 0-1}}
```

## 3. Path B — Azure ML managed online endpoint (BYOC)

Import the image into the workspace ACR (nvcr.io needs auth, so import
rather than reference):
```bash
az acr import --name <acr> \
  --source nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.0 \
  --username '$oauthtoken' --password "$NGC_API_KEY"
```
Then a managed online deployment with `inference_config` routes: liveness
`/v1/health/live`, readiness `/v1/health/ready`, scoring `/v1/ocr`, all
port 8000; instance type from the A10/A100 families. Note AML managed
endpoints don't scale to zero. NVIDIA's maintained samples:
https://github.com/NVIDIA/nvidia-azure-samples (the old
`nim-deploy/cloud-service-providers/azure` tree is deprecated). In Gov:
managed online endpoints are GA in usgovvirginia, but network isolation
for them is listed as unavailable in the cloud-parity doc — review before
handling sensitive images.

## 4. Path C — AKS via the official Helm chart

```bash
helm pull https://helm.ngc.nvidia.com/nim/nvidia/charts/nvidia-nim-nemotron-ocr-v2-2.0.0.tgz \
  --username='$oauthtoken' --password=$NGC_API_KEY
kubectl create secret docker-registry ngc-secret \
  --docker-server=nvcr.io --docker-username='$oauthtoken' --docker-password=$NGC_API_KEY
kubectl create secret generic ngc-api --from-literal=NGC_API_KEY=$NGC_API_KEY
# GPU nodes: AKS GPU node pool (or NVIDIA GPU Operator); then helm install with the secrets
```
The NIM Operator exists but its support for the image-OCR NIM is
unverified — the Helm chart is the documented route.

## 5. Path D — Azure Container Apps serverless GPU (commercial only)

ACA GPU profiles are **T4 and A100 only**; T4 is unsupported by this NIM,
so it's the A100 profile — massive overkill for a 3 GiB model but the only
scale-to-zero option (~$120-200/mo at ~1 GPU-hr/day, 1-3 min cold starts).
**No ACA GPU in Azure Government.** Pull from nvcr.io via registry
credentials (platform capability; not re-verified for ACA specifically).

## 6. Azure Government notes (usgovvirginia)

- SKUs: full NVadsA10_v5 family priced in-region including Spot (strongest
  availability signal; confirm actual quota with `az vm list-skus -l
  usgovvirginia`).
- Marketplace: Gov carries a different image set — plan for stock Ubuntu +
  driver extension, not the NVIDIA VMI.
- NGC egress: nvcr.io is public internet; default outbound works. If
  policy blocks arbitrary egress, **mirror the image into a Gov ACR**
  (`docker pull` on a connected box → `docker push <acr>.azurecr.us/...`)
  and pre-stage weights with `NIM_ENGINE_MODEL_DOWNLOAD_ONLY=1` into the
  `/model` volume — the container otherwise downloads weights from NGC on
  first start.
- NVAIE for Gov: no Gov marketplace offer verifiable; BYOL via NVIDIA
  sales.
- Reminder from the companion research: **the alternative to all of this is
  the plain HF pip package** (open weights, no NIM, no NVAIE) in your own
  CUDA container — same model, same A10 SKUs, no per-GPU surcharge, and
  the only difference is you build the serving layer (FastAPI wrapper)
  yourself. For a Gov deployment that's arguably the cleaner path.

## 7. Fit note for Label Check

`/v1/ocr` with `merge_levels:["word"]` returns exactly what our `Extractor`
Protocol wants: per-word text + confidence + normalized bboxes → scale by
image dims into `Word(text, bbox, conf)` and the locator/rules pipeline
consumes it unchanged. That makes this NIM (or the pip package) a drop-in
**L1.5 candidate** behind the existing seam — worth adding to the M1
`eval-compare` matrix alongside Tesseract and Granite-Docling
(PLAN-us-stack.md).

## Explicitly unverified (from the research pass)

- Azure A10 (non-G) and fractional vGPU profiles aren't on the NIM's
  validated GPU list (expected-compatible, not certified).
- `NIM_HTTP_API_PORT` support for this specific NIM.
- NVIDIA VMI / NVAIE offers in the Gov marketplace; driver-extension Gov
  availability (no exclusion documented, not positively confirmed).
- NIM Operator support for image-OCR; ACA pull-from-nvcr.io specifics.
- Regional capacity/quota (pricing-API presence is a proxy).
- Exact minimum CUDA/driver versions for NIM 2.0.0 (NVIDIA doesn't
  publish them; "current driver + container toolkit" is the requirement).
