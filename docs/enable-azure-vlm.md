# Enabling the Azure VLM (J3 field assist)

Operational guide, 2026-08-03. Companion to
docs/plans/azure-enrichment-layers.md (the design) and
docs/research/azure-frontier-models.md (the model-placement standard that
governs WHERE this may be turned on).

## Status: IMPLEMENTED (plan milestone E1)

`api/vlm.py` carries the provider dialect: `LABELCHECK_VLM_PROVIDER=
off|nvidia|azure` (unset ⇒ nvidia, preserving shipped behavior). The
azure dialect sends the structured content array Azure vision models
require and BOTH auth headers (`Authorization: Bearer` for v1-compatible
endpoints, `api-key` for classic deployment URLs), so either endpoint
form works. A breaker (3 consecutive failures → 30 s cooloff) keeps a
dead endpoint from costing a timeout per crop. All pinned by
`api/tests/test_vlm_providers.py`: dialect payload/headers, off-with-keys
disabled, missing-endpoint silence, breaker trip and recovery.

## Prerequisites

- An Azure OpenAI resource with a **vision-capable deployment** — per the
  placement standard: commercial Foundry frontier (GPT-5.x / Claude 4.6)
  is permitted **only for synthetic/golden data**; a Government-boundary
  deployment (GPT-4.1 class) is the only tier that may ever see real
  pre-approval images, and none is cleared for that yet.
- The deployment's v1-compatible endpoint URL:
  `https://<resource>.openai.azure.com/openai/v1/chat/completions`
- An API key (local dev: `.env`; Azure: Key Vault via managed identity —
  never in the image, never in compose files).

## Enable

1. Add to `.env` (dev) or the environment's Key Vault-backed config:

   ```bash
   LABELCHECK_VLM_PROVIDER=azure
   AZURE_VLM_ENDPOINT=https://<resource>.openai.azure.com/openai/v1/chat/completions
   AZURE_VLM_KEY=<key>            # Key Vault reference in Azure envs
   AZURE_VLM_MODEL=<deployment>   # e.g. gpt-4.1-vision deployment name
   ```

2. Restart the app process (compose: `docker compose -f <profile> up -d
   --force-recreate labelcheck-...` — env_file changes are read at
   container create, not live).

3. **Where it acts:** background layer J3 only — after the provisional
   verdict, for at most `J3_MAX_FIELDS` (3) unresolved amber fields, the
   evidence **crop** (never the full label, 180 KB cap) is sent with one
   targeted question; the answer appears as an "AI suggestion — verify"
   chip on the row. It cannot change any field status (test-enforced).

## Verify it's on

- Run a sample that produces ambers (Samples → "Blurry wine photo").
  Within ~15 s of the provisional, amber rows gain the suggestion chip.
- `api/data/e4-telemetry.jsonl` gains J3 rows; `/healthz` stays `ready`
  (the layer never affects readiness).
- Negative check: remove the key, restart, re-run — results must be
  byte-identical minus the chips (D3; the no-egress test proves the
  same structurally).

## Disable / rollback

Unset `LABELCHECK_VLM_PROVIDER` (or the key) and restart — behavior
reverts byte-identically. At runtime, 3 consecutive failures trip the
breaker (30 s cooloff) and the layer goes quiet on its own; errors never
reach a verdict path.

## Guardrails that enabling does NOT relax

Crops only — a full label never leaves the process. Suggestion-only —
no model output mutates a status; the agent decision path is unchanged,
including the earned-PASS lock. Silent-degrade — outages produce absence,
not errors. Placement standard — dev/test with goldens only until a
boundary is cleared in writing; stage/prod flags stay off by policy.
Prompt-injection posture: suggestions render as escaped text, and the
planted `trap_prompt_injection` golden (plan E2) is the standing
regression once implemented.

## What works today with zero code change (NVIDIA path)

The shipped J3 works now against NVIDIA's hosted endpoint:

```bash
NVIDIA_API_KEY=<key>             # free developer tier, rate-limited
# optional overrides:
# LABELCHECK_VLM_URL=https://integrate.api.nvidia.com/v1/chat/completions
# LABELCHECK_VLM_MODEL=nvidia/llama-3.1-nemotron-nano-vl-8b-v1
```

Same guardrails, same verification steps. This is the fastest way to see
the J3 UX before an Azure subscription is available.
