# Azure DevSecOps CI/CD Plan — dev → test → stage → prod

Status: PLAN (2026-08-03). Companion to docs/deploy-security.md (edge/auth
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

## What this plan deliberately does not do

No per-environment image builds, no mutable tags anywhere past CI, no
cloud AI in any environment holding real data until the model-placement
standard clears a boundary, no scale-out past one writer replica until
the session store grows up, and no unauthenticated public URL under any
circumstances (deploy-security's "no third option" stands).
