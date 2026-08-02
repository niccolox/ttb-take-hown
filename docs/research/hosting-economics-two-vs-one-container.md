# Hosting Economics — Two Containers vs One (Label Check + Nemotron GPU)

Research date: 2026-08-02. Question: what does it cost to host the app as
**one container** (FastAPI + PaddleOCR, CPU only — today's prod shape) vs
**two containers** (CPU app + Nemotron OCR v2 GPU sidecar — the shape
`docker-compose.gpu.yml` ships)? Azure-first (PLAN-us-stack premise),
commercial East US with usgovvirginia deltas. Rates pulled live from the
Azure Retail Prices API and pricing pages on 2026-08-02; monthly = 730 hr.
Companion docs: `nemotron-ocr-azure-deployment.md` (GPU VM runbook, NIM
facts), `nemotron-ocr-local-dev.md` (verified 856 MiB VRAM footprint).

## The one-sentence answer

Two containers is the right *software* shape either way (that's what the
`Extractor` seam is for) — the economics question is really **two
containers on one GPU host vs two hosts (cheap CPU host + scale-to-zero
GPU)**, and the answer flips on GPU duty cycle: below ~14 GPU-hr/day the
split wins on commercial Azure; in Gov there is no serverless GPU, so one
Spot GPU VM running both containers is the only cheap shape.

## Baseline: one CPU container (no GPU at all)

The app needs ~2 vCPU / 4 GB (paddle, M0 measured 2.2 s/label on CPU).
Cheapest always-on homes, East US PAYG:

| Host | Monthly | Notes |
|---|---|---|
| **App Service B3 Linux** | **$48.91** | cheapest managed-container fit (4 vCPU/7 GB) |
| Small VM (B2ms/D2as_v5, 1-yr commit) | $38–41 (+ ~$7 disk/IP) | cheapest overall, most ops burden |
| ACI (2 vCPU/4 GB) | $72.12 | per-second, no scale features |
| ACA Consumption (always-on) | ~$152 | per-second rates punish always-on; ACA only pays off if it scales to zero |
| usgovvirginia uplift | +17–33% | App Service Basic Linux is the outlier at ~+99% |

**~$50/mo is the number to beat.** Any GPU shape is judged against this —
and note the M1 caveat below: the first quality data point (nemotron
dropping "a" in the warning small print) means GPU ≠ automatically better.

## Two containers, ONE host: compose on a single GPU VM

The sidecar needs <1 GiB VRAM measured (English variant, 856 MiB on the
laptop's 4 GB card), so the smallest GPU VM works, and the CPU app rides
on the same VM for $0 marginal:

| SKU (eastus) | VRAM | PAYG/mo | Spot/mo | Gov PAYG / Spot |
|---|---|---|---|---|
| **NV6ads_A10_v5** (1/6 A10) | 4 GB | **$331** | **$61** | $414 / $76 |
| NV12ads_A10_v5 (1/3 A10) | 8 GB | $663 | $122 | $829 / $153 |
| NC4as_T4_v3 (T4) | 16 GB | $384 | $111 | $480 / $139 |
| NV36ads_A10_v5 (full A10) | 24 GB | $2,336 | $432 | $2,920 / $540 |

- Fractional A10 = vGPU/GRID profiles. The **NIM** doesn't validate them;
  our **open-weights Route B container is plain PyTorch/CUDA** and has no
  such gate — and the laptop verification was on a 4 GB GeForce, so the
  4 GB NV6ads slice is the right-size target (verify once; GRID licensing
  is bundled into NV-series pricing).
- Spot at ~82% off is credible for a stateless OCR sidecar
  (`--eviction-policy Deallocate` + restart script; 30 s notice; eviction
  rates only published as portal bands — check at deploy time). Spot
  exists in usgovvirginia (verified via priced meters).
- Flat cost regardless of duty cycle: the GPU bills 24/7 whether OCR runs
  or not.

## Two containers, TWO hosts: CPU app + serverless GPU (commercial only)

ACA serverless GPU profiles today: **T4 and A100 only**, per-second,
scale-to-zero, ~1–2 min cold start (sub-minute achievable with ACR
artifact streaming + weights on a storage mount). **Not available in
Azure Government.** East US supported; East US 2 not on the supported
list despite priced meters — verify at deploy time.

Critical licensing/architecture interaction: **the NIM refuses T4**
(Turing, unsupported) — NIM-on-ACA forces the A100 profile
($1.90/GPU-hr) *plus* NVAIE ($1.00/GPU-hr marketplace or $4,500/GPU/yr).
**The open-weights Route B container has no T4 gate** — rebuild with
`TORCH_CUDA_ARCH_LIST=7.5` (unverified but plain PyTorch; the compose
build arg makes this a one-line change) and it rides the cheap profile
with $0 software surcharge. The two-container seam is what makes this
swap possible at all.

T4 replica sized 4 vCPU/16 GiB ≈ $0.78/hr all-in; app stays on B3
($48.91):

| GPU duty cycle | ACA T4 cost | Total (app + GPU) | vs one NV6ads VM (PAYG $331) |
|---|---|---|---|
| 1 hr/day (pilot/demo) | $24 | **$73/mo** | split wins 4.5× |
| 8 hr/day (business hours) | $190 | **$239/mo** | split wins |
| ~14 hr/day | ~$333 | ~$382 | crossover — VM wins beyond this |
| 24/7 | $570 | $619 | one-host VM wins (or Spot at $61) |

NIM-shaped alternative at 1 hr/day for comparison: A100 meter $58 + NVAIE
$25 + app $49 ≈ **$132/mo** — the "NIM tax" is ~$59/mo at even trivial
duty cycle, before the A100 quota conversation.

## One *merged* container (app + model in one GPU image): don't

- Couples scaling: scale-to-zero takes the whole app down (1–2 min cold
  start on every first user request, not just first OCR).
- Prices the entire app at GPU rates — the CPU work (rules, locator, UI,
  DuckDB sessions) pays the GPU meter.
- Loses the engine seam: paddle fallback and `eval-compare` A/B need the
  OCR engine addressable separately.
- Only defensible case: a single always-on GPU VM where "merged vs
  sidecar" costs identically — and there, compose with two containers
  costs the same and keeps the seam. There is no scenario where the
  merged image wins on money.

## Azure Government (usgovvirginia)

No ACA serverless GPU → the split architecture doesn't exist in Gov.
Cheapest Gov GPU shapes: **one NV6ads VM running both containers —
$414/mo PAYG, $76/mo Spot** — or an AML managed endpoint at the same
$414/mo floor (no scale-to-zero, confirmed; MS recommends 3 instances
for prod → ~$1,242/mo). Gov premium runs ~15–25% over commercial.

## Recommendation (premise-gated, matches PLAN-us-stack)

1. **Today / pilot: stay one CPU container (~$49/mo).** The GPU engine is
   an M1 `eval-compare` candidate, not a proven upgrade — the first
   quality data point cuts against it.
2. **If M1 says nemotron earns its keep, commercial:** keep the app on
   B3, put the Route B container (rebuilt for arch 7.5) on ACA serverless
   T4 — **$73–239/mo** across realistic duty cycles, $0 NVIDIA licensing.
3. **Gov:** compose both containers onto one NV6ads (Spot if eviction
   tolerance allows: **$76/mo**; PAYG $414).
4. **Never** merge the app into the GPU image, and avoid the NIM unless
   something needs its serving layer — it forecloses T4/fractional-A10
   economics and adds NVAIE.

## Explicitly unverified

- Route B container on T4 (needs the arch-7.5 rebuild + a smoke run) and
  on an NV6ads vGPU slice — both expected-fine plain-CUDA, neither tested.
- ACA East US 2 serverless-GPU support (meters priced, region not listed).
- Spot eviction bands for these SKUs at deploy time (portal-only data).
- NVAIE marketplace $1/GPU-hr is labeled promotional by NVIDIA.
- ACA cold-start mitigation (artifact streaming + weight mount) against
  our specific ~530 MB weight set.

Sources: Azure Retail Prices API (2026-08-02 snapshots, eastus/eastus2/
usgovvirginia); azure.microsoft.com pricing pages (container-apps,
container-instances, app-service/linux, virtual-machines/linux,
machine-learning); learn.microsoft.com (gpu-serverless-overview,
workload-profiles, managed-online-endpoints VM SKU list); docs.nvidia.com
NVAIE licensing-guide pricing; Azure Marketplace NVAIE listing.
