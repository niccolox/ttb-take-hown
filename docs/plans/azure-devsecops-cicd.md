# Azure DevSecOps CI/CD Plan — dev → test → stage → prod

Status: PLAN (2026-08-03; quick-start playbook + AI-layer config added 2026-08-05). Companion to docs/deploy-security.md (edge/auth
posture and DECIDE items), docs/research/azure-frontier-models.md (model
placement standard), docs/research/devsecops-audit-nist.md (control
evidence), and the docs/todo.md deployment backlog (WAF, SSO, magic link,
env modes, audit log, feature flags). Everything below extends what exists
— the GitHub Actions CI, the digest-pinned non-root image, the hash-locked
supply chain — rather than replacing it.

## Principles

1. **Build once, promote by digest.** One image is built and signed at CI;
   dev/test/stage/prod run the same digest. No environment ever builds its
   own image; rollback = redeploy the previous digest.
2. **Fail-closed gates.** A promotion happens because evidence exists, not
   because a human is confident. Every gate below names its artifact.
3. **No-egress by default at every tier.** Cloud AI layers (J3/J4) are
   opt-in per environment under the model-placement standard; prod holding
   real pre-approval data runs with cloud flags OFF until the standard
   clears a boundary for it.
4. **FIPS 199 M/M/L** (deploy-security.md) → 800-53 moderate is the
   control target from stage upward. Dev/test never hold real data, which
   is what keeps their gates lighter.
5. **OIDC everywhere, secrets nowhere.** Pipelines federate to Azure via
   workload identity (no PATs, no service-principal secrets in CI); apps
   read secrets from Key Vault via managed identity; `.env` files exist
   only on developer laptops.

## Environment topology

| Env | Where | Data allowed | Cloud AI | Auth | Purpose |
|---|---|---|---|---|---|
| **dev** | local compose + ephemeral Azure Container Apps (ACA) revision | synthetic/golden only | J3 dev-tier allowed (goldens only) | none (loopback) / long random URL | fast iteration |
| **test** | ACA, isolated env | synthetic/golden + BAM/anatomy fixtures | off | Entra ID (team group) | automated verification incl. OCR evals |
| **stage** | ACA or App Service, prod-mirror config | real-SHAPED data (masked COLA fields); no real images until DECIDE | off | Entra ID + WAF | pre-prod checklist, DAST, pilot rehearsal (mother test) |
| **prod** | ACA/App Service; Azure **Government** the moment real pre-approval data lands | real data per records decisions | OFF (policy, not just default) | Entra ID / PIV per deploy-security DECIDE + Front Door WAF | the pilot |

Environment mode surfaces in the app as `LABELCHECK_ENV=dev|test|stage|prod`
(todo item "create dev, stage, prod mode"): banner badge in non-prod, the
COLA Cloud registry pipelines feature-flagged OFF in prod (todo), sample/
eval menus hidden in prod, rate limits per env.

## Azure service mapping

- **Registry:** Azure Container Registry (Premium) — content trust +
  **cosign/notation signing at push**; admission checks the signature at
  deploy (closes the provenance line the container audit left to
  deployment). Geo-replication only if prod goes multi-region.
- **Pipelines:** keep GitHub Actions (the CI already exists) + environments
  with required reviewers for stage/prod; OIDC federation to Azure.
  Azure DevOps Pipelines is the drop-in alternative if Treasury tenancy
  requires it — the gate list below is host-agnostic.
- **Secrets:** Key Vault per env (`COLACLOUD_API_KEY` dev/test only;
  future `AZURE_OPENAI_*` per placement standard; `NVIDIA_API_KEY`
  dev-tier only). Managed identity, no connection strings.
- **Edge:** Azure Front Door + WAF policy (todo: waf, bot management) —
  rate limiting at edge complements the app's per-IP bucket; the
  "magic link" demo pattern = Front Door route with a long random path +
  IP allowlist, explicitly the deploy-security escape hatch only.
- **Identity:** Entra ID (deploy-security option 1) now; PIV/CAC via
  agency SSO (option 2) when it fronts real reviewers. "SSO" todo item.
- **Observability:** Log Analytics workspace per env; container stdout +
  `/healthz` scrape (including `telemetry_drops`); Defender for
  Containers on ACR + runtime — continuous CVE scanning is the standing
  answer to unpatched-upstream base CVEs (the current python:3.12-slim
  pin matches upstream and still carries 2C/2H — pin-churn can't fix
  what upstream hasn't patched; visibility + the bump ritual can).
- **Storage:** `api/data` on Azure Files/managed disk (encrypted at rest,
  platform default) — DuckDB single-writer means ONE replica owns the
  volume; scale-out waits for the session-store rework (recorded risk).
- **IaC:** Bicep in-repo (`infra/`), deployed by the same pipeline —
  environments differ by parameter file only.

## The pipeline (stages and gates)

### Stage 0 — CI (exists today, runs on every push/PR)
Hash-locked install → pytest (208) → no-egress proof → pip-audit
(advisory) → axe (0 violations). **Artifact:** test report.
*Additions:* `gitleaks` secret scan; `LABELCHECK_OCR_EVAL=1` anatomy e2e
on a nightly schedule (too slow per-push).

### Stage 1 — Build, scan, sign (extends the weekly image job to per-merge)
Build the digest-pinned image → post-bake model-integrity gate (exists)
→ non-root + no-data assertions (exist) → trivy/Defender scan (**gate:**
no NEW critical vs. the triaged baseline; report-only for inherited base
CVEs) → SBOM regenerated and **attached to the image** (ORAS/ACR
artifact) → cosign sign → push to ACR. **Artifact:** signed digest +
SBOM + scan report. This digest is the only thing that moves forward.

### Stage 2 — dev (auto-deploy on merge to main)
Deploy digest to ACA dev → `/healthz` ready + state check → `smoke.sh`
against the revision (poll-until-settled, exists) → golden sweep subset.
**Gate to test:** smoke green. **Artifact:** smoke log.

### Stage 3 — test (auto after dev, blocking)
Full golden + BAM + anatomy e2e via the real OCR path
(`LABELCHECK_OCR_EVAL=1`) → determinism check (same image → same settled
verdict, 3/3 — exit criterion already ratified) → batch physics run (300
labels: p50 latency, drain rate, RSS ceiling vs. the measured baselines)
→ live axe against the running app. **Gate to stage:** all green +
required-reviewer approval. **Artifact:** eval report with the numbers
beside their baselines.

### Stage 4 — stage (manual promote)
Prod-mirror config (TLS at edge, Entra auth, WAF ON, cloud flags OFF,
`LABELCHECK_ALLOWED_HOSTS` set — the deploy-security pre-flight checklist
becomes a pipeline step that FAILS if any box is unchecked) → OWASP ZAP
baseline scan (auth-aware) → the **mother test** rehearsal per
docs/mother-test-protocol.md against stage → 24h soak with Log Analytics
alerts quiet (`telemetry_drops` == 0, no 5xx, RSS flat). **Gate to
prod:** checklist artifact + ZAP report + soak dashboard + human
approval (change record). **Artifact:** the promotion package — this is
the M-22-18-adjacent evidence bundle.

### Stage 5 — prod (manual, change-controlled)
Slot/revision deploy of the SAME digest → health + smoke → traffic swap
(ACA revision weights: 10% → 100% or blue/green) → previous digest kept
hot for instant rollback. Post-deploy: no-egress verification against
the live instance (the deploy-security checklist's last line).

## Config matrix (the LABELCHECK_* contract per env)

| Flag | dev | test | stage | prod |
|---|---|---|---|---|
| `LABELCHECK_ENV` | dev | test | stage | prod |
| `LABELCHECK_JOBS` | on | on | on | on (local layers only) |
| J4 / cloud AI flags | off (opt-in) | off | off | **off — policy** |
| `LABELCHECK_MM_READ` (mm second read) | on (goldens) | on (goldens) | off | **off — policy** |
| `LABELCHECK_VLM_PROVIDER` | fixture / gpt41 | fixture | off | off |
| `AZ_BASE` + `AZ_OPENAI_MODEL` (one-value model switch) | Key Vault | Key Vault | unset | unset |
| `NEMOTRON_INFER_LENGTH` | 1536 (GPU shapes) | 1536 | 1536 | 1536 |
| `LABELCHECK_RATE_RPM` | 120 | 120 | 60 | per-audience decision |
| `LABELCHECK_ALLOWED_HOSTS` | loopback | test host | stage host | prod host(s) |
| COLA Cloud pipelines | on | on | off | **feature-flagged off** |
| Samples/eval menus | on | on | on | off (runbook + tour stay) |

## Rollout sequencing

1. **M1 (exists):** Stage 0 CI — needs only the user's first push.
2. **M2 (~1 day):** Stage 1 — promote the weekly image job to per-merge,
   add cosign + SBOM-attach + gitleaks; ACR + OIDC federation via Bicep.
3. **M3 (~1–2 days):** dev + test ACA environments, smoke + eval gates
   wired (the scripts already exist; this is plumbing).
4. **M4 (~2 days + DECIDE items):** stage with edge/auth/WAF per
   deploy-security; checklist-as-pipeline-step; ZAP.
5. **M5 (thin):** prod promote path + rollback drill (deploy N-1 digest
   on purpose, prove it).


## Quick-start playbook — day one to a dev URL

The condensed path from this repo to a running **dev** deployment (the
M2+M3 essentials), each step naming its gate. Prereqs: `az` CLI logged
into the target subscription, this repo pushed to GitHub, Docker local.
Names are variables — pick once, reuse everywhere.

```bash
export RG=labelcheck-dev  LOC=eastus  ACR=labelcheckacr  APP=labelcheck-dev
```

**1 · Resource group + registry (once).**
```bash
az group create -n $RG -l $LOC
az acr create -n $ACR -g $RG --sku Premium
```

**2 · Build once, push by digest** (Principle 1 — the same digest moves
through every env; no cloud rebuilds).
```bash
az acr login -n $ACR
docker build -t $ACR.azurecr.io/labelcheck:$(git rev-parse --short HEAD) .
docker push $ACR.azurecr.io/labelcheck:$(git rev-parse --short HEAD)
DIGEST=$(az acr repository show -n $ACR --image labelcheck:$(git rev-parse --short HEAD) --query digest -o tsv)
```
*Gate:* the image build already runs the post-bake model-integrity
assert and non-root checks — a failed bake never produces a digest.
(M2 later promotes this to CI with cosign + SBOM-attach; the playbook
gets you moving today.)

**3 · Key Vault + secrets — the WHOLE `.env`, split correctly**
(Principle 5 — the laptop file is the SOURCE; secrets land in the
vault, non-secret config rides as plain env vars; nothing typed,
nothing echoed).
```bash
az keyvault create -n $APP-kv -g $RG -l $LOC -o none
# wait for real DNS before touching secrets (fresh vaults can lag)
until az keyvault show -n $APP-kv -o none 2>/dev/null \
      && getent hosts "$APP-kv.vault.azure.net" >/dev/null; do sleep 5; done
# parse rather than source — a stray placeholder like FOO=<bar> would
# break `source`, and parsing executes nothing. Every variable whose
# name contains KEY is a secret → Key Vault (names hyphenated; step 5's
# secretrefs use the same mapping). `-o none` matters: without it az
# prints the secret bundle INCLUDING the value into your terminal log.
while IFS='=' read -r K V; do
  [[ "$K" =~ ^[A-Z][A-Z0-9_]*$ && -n "$V" ]] || continue
  if [[ "$K" == *KEY* ]]; then
    az keyvault secret set --vault-name $APP-kv \
      -n "${K//_/-}" --value "$V" -o none
  fi
done < .env
# everything else is CONFIG, not secret — emit it as the --env-vars
# fragment for steps 4/5 (URIs, model names, flags, endpoints):
while IFS='=' read -r K V; do
  [[ "$K" =~ ^[A-Z][A-Z0-9_]*$ && -n "$V" && "$K" != *KEY* ]] || continue
  printf '%s=%s \\\n' "$K" "$V"
done < .env
```
Today that puts COLACLOUD_API_KEY, AZ_OPENAI_API_KEY, AZ_GPT_4_1_KEY,
AZ_GPT_5_1_SOL_KEY, MISTRAL_OCR_KEY and FOUNDRY_API_KEY in the vault,
and emits the config set (AZ_BASE, AZ_OPENAI_MODEL, AZ_*_URI,
MISTRAL_OCR_ENDPOINT, LABELCHECK_* flags, NEMOTRON_* — plus any future
additions) for the container. Two deliberate exceptions when copying
the emitted config into step 4: drop `NEMOTRON_OCR_URL` (localhost is
meaningless in ACA — set it only with the GPU upgrade) and drop
`OPENAI_DEBUG` (prompts contain application values; dev-only on
laptops). **Live state (2026-08-05):** this exact flow ran against the
subscription — vault **`labelcheck-dev-kv`** exists (the plain name was
free; the original resolve failure was simply that it had never been
created) holding AZ-GPT-4-1-KEY, AZ-GPT-5-1-SOL-KEY, AZ-OPENAI-API-KEY,
COLACLOUD-API-KEY, FOUNDRY-API-KEY, with Key Vault Secrets Officer
granted at the RG scope.

**3a · Prove the vault path first:** `RG=$RG LOC=$LOC
./scripts/hello_azure_keyvault.sh` — creates a disposable vault, waits
for real DNS, round-trips a secret, deletes AND purges. Run live on
this subscription it caught both failure classes in order: the
name-resolution miss (3b below) and the RBAC-mode 403 (fixed durably
with the data-plane role at the RESOURCE-GROUP scope, so every future
vault in the RG inherits it):
`az role assignment create --assignee $(az ad signed-in-user show --query id -o tsv) --role "Key Vault Secrets Officer" --scope $(az group show -n $RG --query id -o tsv)`

**3b · Vault recovery** — when the seeding loop fails with
`Failed to resolve '<vault>.vault.azure.net'`: the vault does not exist
at that name. Key Vault names are **globally** unique across all of
Azure — `$APP-kv` can be taken by anyone, or held by a soft-deleted
vault — and a freshly created vault can also lag DNS by a minute. This
block finds-or-creates a vault with a unique suffix, waits until the
name actually resolves, then re-runs the seed:
```bash
# reuse an existing vault in the RG if one exists; else mint a unique name
KV=$(az keyvault list -g $RG --query "[0].name" -o tsv)
if [ -z "$KV" ]; then
  KV="$APP-kv-$(az account show --query id -o tsv | cut -c1-8)"
  az keyvault create -n "$KV" -g $RG -l $LOC -o none \
    || az keyvault recover -n "$KV" -o none    # reclaim a soft-deleted name
fi
echo "vault: $KV"
# wait for BOTH the control plane and DNS before touching secrets
until az keyvault show -n "$KV" -o none 2>/dev/null \
      && getent hosts "$KV.vault.azure.net" >/dev/null; do
  echo "waiting for $KV.vault.azure.net…"; sleep 5
done
# re-seed (same parse-never-source loop as step 3)
while IFS='=' read -r K V; do
  [[ "$K" =~ ^[A-Z][A-Z0-9_]*$ && -n "$V" && "$K" == *KEY* ]] || continue
  az keyvault secret set --vault-name "$KV" -n "${K//_/-}" --value "$V" -o none
done < .env
az keyvault secret list --vault-name "$KV" --query "[].name" -o tsv   # names only
```
From here on, use `$KV` wherever the playbook says `$APP-kv` (step 5's
set-policy and secretrefs). If the seed loop returns **403 Forbidden**
instead, the vault was created in RBAC mode and your CLI identity needs
the data-plane role:
`az role assignment create --assignee $(az ad signed-in-user show --query id -o tsv) --role "Key Vault Secrets Officer" --scope $(az keyvault show -n "$KV" --query id -o tsv)`

The repo's `.env` is plain `KEY=value` lines — the loaders, compose,
and these parsers all depend on that; keep comments on their own lines
(a live dry-run of this exact loop caught an unquoted `<placeholder>`
line that would have broken `source` — hence parse, never source).

**4 · Container Apps environment + the app.** Dev-cloud runs the
**CPU shape** (paddle-primary: `LABELCHECK_EXTRACTOR` unset) — the
Nemotron sidecar needs a GPU workload profile, which is the documented
upgrade, not the day-one path.
```bash
az containerapp env create -n $APP-env -g $RG -l $LOC
az containerapp create -n $APP -g $RG --environment $APP-env \
  --image $ACR.azurecr.io/labelcheck@$DIGEST \
  --registry-server $ACR.azurecr.io --system-assigned \
  --ingress external --target-port 8123 \
  --min-replicas 1 --max-replicas 1 \
  --env-vars LABELCHECK_ENV=dev LABELCHECK_ALLOWED_HOSTS='<fqdn>' \
             LABELCHECK_MM_READ=1 LABELCHECK_VLM_PROVIDER=fixture
```
`--max-replicas 1` is load-bearing: DuckDB single-writer (recorded
risk). The fixture provider gives the keyless mm-second-read demo with
zero egress; flip to real providers only via Key Vault references.
*Gate:* `curl https://<fqdn>/healthz` → `"ready":true`, then
`scripts/smoke.sh` against the URL.

**5 · Wire Key Vault references** (managed identity was created by
`--system-assigned`).
```bash
az keyvault set-policy -n $APP-kv --object-id $(az containerapp show -n $APP -g $RG --query identity.principalId -o tsv) --secret-permissions get
az containerapp update -n $APP -g $RG --set-env-vars \
  COLACLOUD_API_KEY=secretref:colacloud-api-key \
  AZ_BASE='https://<resource>.cognitiveservices.azure.com' \
  AZ_OPENAI_MODEL=gpt-5.6-sol
```
The one-value model switch works in the cloud exactly as locally:
`AZ_OPENAI_MODEL` picks the deployment for the text layers AND the
vision second read; pin `LABELCHECK_VISION_MODEL=gpt-4.1` wherever the
Gov-parity story matters (no GPT-5.x in Azure Government).

**6 · Storage for sessions.**
```bash
az storage account create -n ${APP//-/}sa -g $RG -l $LOC --sku Standard_LRS
# create an Azure Files share, mount at /app/api/data (one writer!)
az containerapp env storage set -n $APP-env -g $RG --storage-name sessions \
  --azure-file-account-name ${APP//-/}sa --azure-file-share-name sessions --access-mode ReadWrite
```

**7 · Prove the posture before sharing the URL** (deploy-security
pre-flight, abbreviated for dev):
- `/healthz` ready; rate limiter answers 429 under a burst
- no-egress spot check: with fixture provider, Log Analytics shows zero
  outbound AI calls
- the long-random-URL escape hatch ONLY until Entra fronts it — never
  a bare public URL past dev

**8 · Tear-down / rollback.** Rollback is `az containerapp update
--image ...@<previous digest>`; tear-down is `az group delete -n $RG`.
Nothing in dev is precious — that is the point of synthetic-only data.

**GPU upgrade (optional, when dev needs the primary engine):** add a
GPU workload profile to the ACA environment (or an NC-family VM running
`docker-compose.gpu.yml`), deploy the Nemotron sidecar with
`NEMOTRON_INFER_LENGTH=1536` (the adopted default — kills the statutory
small-print dropout), point the app at it via `NEMOTRON_OCR_URL` and
`LABELCHECK_EXTRACTOR=nemotron`. Until then, dev-cloud is
paddle-primary and the J-layer QA story still holds.

**What day one explicitly is NOT:** not test/stage/prod (those follow
the gated pipeline above), not real data (synthetic/golden only), not
public (allowed-hosts + auth posture first), not a substitute for M2's
signing/SBOM CI — the playbook exists so the first URL happens this
week while the gates get built.

## What this plan deliberately does not do

No per-environment image builds, no mutable tags anywhere past CI, no
cloud AI in any environment holding real data until the model-placement
standard clears a boundary, no scale-out past one writer replica until
the session store grows up, and no unauthenticated public URL under any
circumstances (deploy-security's "no third option" stands).
