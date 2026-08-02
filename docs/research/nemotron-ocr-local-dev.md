# Nemotron OCR v2 — Local Dev Deployment (NVIDIA Docker)

Research date: 2026-08-02. Scope: running Nemotron OCR v2 locally for
development on this machine using NVIDIA Docker (nvidia-container-toolkit).
Status: machine diagnosis and container facts are verified; a research pass
on GeForce/NIM compatibility, the HF pip-package specifics, and
ONNX/CPU alternatives is IN FLIGHT — findings will be appended when it
completes. Companion docs: `nemotron-ocr-azure-deployment.md` (container
facts, API shape), `nvidia-ocr-lineage-azure.md` (lineage/licensing).

---

## This machine (diagnosed live, 2026-08-02)

| Item | State |
|---|---|
| OS / kernel | Ubuntu 24.04, kernel **7.0.0-28-generic** |
| GPU | **GeForce RTX 3050 Ti Mobile** (GA107, Ampere, **4 GB VRAM**) + Intel iGPU (hybrid) |
| Docker | 29.4.1 with `nvidia` runtime registered |
| nvidia-container-toolkit | 1.19.0 installed |
| Driver | `nvidia-driver-580-open` installed **but not functional** |

**Root cause of the dead driver (diagnosed, not speculative):** every
`linux-modules-nvidia-580-open-<kernel>` package on the system is in `rc`
(removed) state for older kernels, and the modules package for the RUNNING
kernel was never installed after the kernel upgraded to 7.0.0-28. Secure
Boot is disabled (not a MOK issue); dkms is empty (Ubuntu uses prebuilt
signed module packages for -generic kernels, not dkms). The package exists
in the archive.

**Fix (needs sudo):**
```bash
sudo apt install -y \
  linux-modules-nvidia-580-open-7.0.0-28-generic \
  linux-modules-nvidia-580-open-generic-hwe-24.04
sudo modprobe nvidia
nvidia-smi   # should now show the RTX 3050 Ti
```
The `-generic-hwe-24.04` meta package keeps modules arriving with future
kernel upgrades so this doesn't recur.

## VRAM math on a 4 GB card

| Variant | FP16 footprint (NVIDIA support matrix) | Fits 4 GB? |
|---|---|---|
| **English** (53.8M params) | **1.6-2.1 GiB** | Yes, comfortably — the local-dev choice |
| Multilingual (83.9M) | 2.7-3.2 GiB | Tight — desktop session + CUDA context overhead may push it over; not recommended here |

Label Check is an English-label use case — the English variant is the right
dev target anyway.

## Route A — NIM container (fastest to a running endpoint)

Prereqs: driver fixed (above); free NGC API key
(https://org.ngc.nvidia.com/setup/api-keys) — **free Developer Program key
covers local dev/test**; production would need NVAIE.

```bash
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
export LOCAL_NIM_CACHE=~/.cache/nim && mkdir -p "$LOCAL_NIM_CACHE"/{cache,weights}

docker run -it --rm --name nemotron-ocr-dev \
  --runtime=nvidia --gpus all --shm-size=16GB \
  -e NGC_API_KEY \
  -e NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc \
  -e NIM_PERFORMANCE_MODE=0 \
  -v "$LOCAL_NIM_CACHE/cache:/opt/cache" \
  -v "$LOCAL_NIM_CACHE/weights:/model" \
  -u $(id -u) -p 8123:8000 \
  nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.0
# note: -p 8123:8000 avoids colliding with... actually Label Check uses 8123.
# Use 8200:8000 locally: -p 8200:8000
```

Verify:
```bash
curl http://localhost:8200/v1/health/ready
curl -X POST http://localhost:8200/v1/ocr -H 'Content-Type: application/json' \
  -d '{"input":[{"type":"image_url","url":"data:image/png;base64,'"$(base64 -w0 label.png)"'"}],"merge_levels":["word"]}'
```

Compose snippet (dev, GPU reservation syntax):
```yaml
services:
  nemotron-ocr:
    image: nvcr.io/nim/nvidia/nemotron-ocr-v2:2.0.0
    environment:
      - NGC_API_KEY=${NGC_API_KEY}
      - NIM_ENGINE_MODEL_DOWNLOAD_PROVIDER=ngc
      - NIM_PERFORMANCE_MODE=0
    volumes:
      - nim-cache:/opt/cache
      - nim-weights:/model
    ports: ["8200:8000"]
    shm_size: 16gb
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
volumes: { nim-cache: {}, nim-weights: {} }
```

**Open question (research in flight):** the NIM's validated-GPU list is
datacenter cards + RTX PRO 6000 — GeForce RTX 30-series is Ampere and
expected to work, but consumer-GPU behavior (compute-capability checks,
profile selection, 4 GB floor) is being verified. If the NIM refuses the
GeForce card, Route B is the fallback.

## Route B — the HF repo's OWN Dockerfile (RECOMMENDED for this laptop)

Research verdict (verified 2026-08-02): **the HF repo ships an official
Dockerfile and docker-compose.yaml** — base image
`nvcr.io/nvidia/pytorch:25.09-py3`, builds the C++/CUDA extension with
`BUILD_CPP_FORCE=1 pip install -v . --no-build-isolation`, honors
`TORCH_CUDA_ARCH_LIST` as a build arg (set `"8.6"` for GA107). This
**sidesteps every host build requirement** (CUDA toolkit + nvcc, exact
Python 3.12, matching torch CUDA wheels) — only the driver +
nvidia-container-toolkit are needed on the host, both of which this machine
has (post driver fix).

```bash
git lfs install
git clone https://huggingface.co/nvidia/nemotron-ocr-v2   # ~553 MB
cd nemotron-ocr-v2
docker compose build   # TORCH_CUDA_ARCH_LIST=8.6 as build arg for GA107
docker compose run --rm nemotron-ocr bash -lc \
  "python example.py ocr-example-input-1.png --merge-level word"
```

In-code API (verbatim from the card):
```python
from nemotron_ocr.inference.pipeline_v2 import NemotronOCRV2
ocr = NemotronOCRV2(lang="en")     # English — the 4 GB choice (default is multilingual)
predictions = ocr("label.png")      # [{text, confidence, left, upper, ...}]
```
Memory-saving modes documented on the card: detector-only (~37% less GPU
memory) and skip-relational (~35% less, ~8% faster). `merge_level`:
word/sentence/paragraph.

Bare-metal pip variant (if you want it outside Docker): torch first from
the cu128 index, then `pip install --no-build-isolation -v .` with nvcc on
PATH matching the torch CUDA version; Python `>=3.12,<3.13` exactly
(Ubuntu 24.04's native 3.12 qualifies).

No NGC key, no NIM, no NVAIE — open weights under the NVIDIA Open Model
License. Output maps directly onto the `Extractor` Protocol → this is the
containerized form of the M1 `eval-compare` candidate (PLAN-us-stack.md
L1.5).

## Route A caveat (researched): NIM on GeForce is risky — prefer Route B

NVIDIA's general NIM policy says any GPU with compute capability ≥ 8.0 and
enough memory "will run," and GA107 (8.6) passes — but real-world GeForce
reports are bad: an RTX 4090 hit "0 compatible profiles / non-free GPU" in
the NIM profile selector
([forum](https://forums.developer.nvidia.com/t/rtx-4090-shows-as-non-free-gpu-when-running-nim-model-in-docker/295740)),
and a sibling Nemotron NIM ships only large-batch profiles that OOM on
consumer cards. No report exists either way for the OCR NIM on GeForce.
On a 4 GB GeForce the realistic risks are profile-selection failure or
throughput-profile OOM. **Use Route B locally; save the NIM for
datacenter GPUs (the Azure runbook).**

## Lighter alternatives — researched, closed

- **ONNX export: none exists.** The repo ships PyTorch checkpoints + the
  compiled CUDA extension only; no ONNX mention anywhere.
- **CPU fallback: effectively impossible as shipped.** The pipeline imports
  a CUDA extension built at install; no CPU path is documented. A
  driverless/CPU requirement means a different engine (Tesseract), not
  this model.

## GeForce/4 GB expectations (flagged honestly)

Architecture-compatible (Ampere), nothing in the pip package gates on GPU
model, and English FP16 measures 1.57-2.23 GiB in the NIM — expect
~2-2.5 GiB under PyTorch overhead, fitting 4 GB at batch 1 with
`lang="en"` (use detector-only/skip-relational modes if tight). **No
published report of a 4 GB consumer-GPU run exists either way — this
machine's attempt will be the data point.** Multilingual (2.7-3.3 GiB) is
not recommended here.

## Fit note

Local dev target: Route B container exposed on :8200, wrapped by a thin
adapter implementing `Extractor.extract() -> list[Word]` (scale normalized
bboxes by image dims, conf already 0-1), plugged into `make eval-compare`
as the `nemotron` engine — runs on this laptop's 3050 Ti with the English
variant.
