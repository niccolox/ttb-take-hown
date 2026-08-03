# DevSecOps Audit — Treasury/Federal + NIST Standards Mapping

> **Re-audited 2026-08-03 (evening)** against the post-remediation tree —
> all ten findings verified CLOSED and the surface added since (telemetry
> endpoint, guided tour, runbook, ingested reference assets, new rules
> modules) assessed. See **“Re-audit — current implementation”** at the end;
> the body below is preserved as the original audit record.

Audit date: 2026-08-03, main @ bcc17df. Scope: this repository as built —
code, containers, dependencies, data flows, UI — assessed against the
frameworks a Treasury/TTB deployment would face. Every finding cites the
actual repo state; no generic checklist items. Companion evidence:
docs/research/ai-supply-chain-risk.md, us-supply-chain-policy.md,
api/integrity.py, api/requirements.lock, PLAN-enrichment.md AD-31.

Frameworks applied: NIST SP 800-218 (SSDF), SP 800-53r5 (moderate-baseline
control families), SP 800-190 (container security), SP 800-161r1 + EO 14028
/ OMB M-22-18 (software supply chain), 2026 SBOM Minimum Elements
(CISA/NSA/FBI), NIST AI RMF 1.0, FIPS 199, Section 508, with Treasury
TD P 85-01 posture assumed for context.

## Executive summary

The project's supply-chain and input-hardening posture is unusually strong
for a prototype — hash-locked dependencies, integrity-pinned model weights,
no-egress runtime, per-IP rate limiting, host validation, audited
refinement provenance. The dominant gaps are PROCESS, not code: **no CI
pipeline exists**, so every gate that matters (tests, no-egress proof,
dependency audit, image scan) runs only when a human remembers; the
container runs as root; local images can bake session data; and the SBOM
attestation artifact required by M-22-18 is still an open TODO. FIPS 199
categorization: pre-approval label data is sensitive-but-unclassified
commercial information → **Moderate confidentiality** is the defensible
categorization, which makes the auth-less loopback design acceptable ONLY
while undeployed.

## Scorecard

| Area | Grade | One-line basis |
|---|---|---|
| Supply chain (800-161, EO 14028) | B+ | locks + weight pinning shipped; SBOM + attestation open |
| Secure development (SSDF 800-218) | C+ | strong practices, zero automation (no CI) |
| Container security (800-190) | C- | root user, no .dockerignore, mutable base tags |
| Access control / network (800-53 AC/SC) | B- | loopback + Host validation + rate limits; no TLS/authn story yet (deploy-blocked, documented) |
| Audit & accountability (800-53 AU) | B | provenance on every verdict change; no centralized/log-retention story |
| AI risk (AI RMF 1.0) | B+ | screening-not-approval posture, dual-engine guard, honest-degrade doctrine, calibration telemetry |
| Accessibility (508) | B | 3px focus rings, aria labels, 44px targets; no formal VPAT/testing |

## Findings

### F1 — No CI/CD pipeline: every security gate is manual. HIGH.
`.github/workflows/` does not exist. The suite (159 tests), the smoke
budget, `pip --require-hashes` install, and the model-integrity check all
exist but run only on demand. PLAN-enrichment references a "no-egress CI
job" (J4 byte-identical assertion) that is ASPIRATIONAL — no such job
exists. SSDF PW.7/PW.8/RV.1 expect automated verification on every change.
**Fix:** one workflow: pytest + `pip install --require-hashes` (proves the
lock) + `python -m api.integrity check` against a cached model layer +
image build + `pip-audit`/`trivy` scan + a no-network test step
(`--disable-socket` via pytest-socket) proving the no-egress claim. ~1 day.

### F2 — Container runs as root. HIGH (800-190 §4.4.2, 53r5 CM-6/AC-6).
No `USER` directive in the Dockerfile; uvicorn serves as uid 0. A container
escape or SSRF-to-file-write lands with root in the container. The GPU
sidecar (NGC base) likewise. **Fix:** create app user, chown /app,
`USER app`; paddle/models path moves under the user's home
(`LABELCHECK_MODELS_DIR` already parameterizes it). ~1 hour incl. rebuild
verification against the healthcheck.

### F3 — Local image builds can bake session data. HIGH (53r5 SC-28/MP-6).
No `.dockerignore` exists and the Dockerfile does `COPY api/ api/` —
`api/data/` (DuckDB session store containing REVIEWED LABEL IMAGES) and
`api/eval/colacloud/` (pulled registry corpus) ride into any locally built
image if present on disk. An image pushed to a registry ships review data.
**Fix:** `.dockerignore` with `api/data/`, `api/eval/colacloud/`,
`api/eval/batches/`, `.env`, `.venv/`, `vendor/`. ~10 minutes; highest
value-per-line in this audit.

### F4 — SBOM + M-22-18 attestation artifact still open. MEDIUM-HIGH.
Tracked in TODOS (P2) with the right spec (2026 SBOM Minimum Elements:
component hash, license, generation context; PRC-origin annotation for
paddle lineage). The hash lock (1,119 hashes) makes generation nearly
mechanical (`pip-audit --format cyclonedx` / syft). Until it exists, an
M-22-18 self-attestation package cannot be assembled. **Fix:** generate
CycloneDX in the F1 workflow, commit per release. ~half day incl. the
PRC-annotation pass from the existing research doc.

### F5 — No TLS/authn design for the deployed URL. MEDIUM (deploy-gated).
Auth-less loopback is DOCUMENTED as intentional (compose comments, AD-31
"result endpoints inherit the deployed-URL work's auth and are blocked
from deploy until it exists" — the right control language). But the
deployed-URL P1 has no companion security design: no TLS termination
choice, no authn model (PIV/PIV-I would be the Treasury-native answer;
a reverse-proxy Entra/OAuth front is the pragmatic one), no session
security. **Fix:** one-page deploy security spec before any `az` command:
TLS at the platform edge, authn at a proxy, `LABELCHECK_ALLOWED_HOSTS`
set, rate limits reviewed for public exposure.

### F6 — Logging is operational, not evidentiary. MEDIUM (53r5 AU-2/AU-9/AU-11).
Refinement provenance (layer/engine/from/to per verdict change) and agent
decision stamps are genuinely good AU-story pieces — but they live in the
result payload/session store only. Uvicorn logs are stdout-ephemeral; the
E4 telemetry jsonl grows unbounded with no rotation/retention policy; no
integrity protection on any log. No secrets appear in logs (verified:
key names never logged). **Fix:** define retention (e.g., session store =
system of record for decisions; telemetry rotated at N MB); document that
compose/host log drivers own AU-4/AU-9 in deployment.

### F7 — Dependency currency process is undefined. MEDIUM (SSDF PW.4, 800-161).
The lock is a point-in-time snapshot (good); nothing schedules re-audit.
`colacloud` pin (0.4.4 declared / 0.4.2 installed per earlier probe —
verify) and the paddle pins are load-bearing and now triple-locked
(version + hash + weight digest), which makes UPGRADE deliberate but also
means CVE response is fully manual. **Fix:** `pip-audit` in CI (F1) +
a documented monthly refresh ritual (regenerate lock → suite → golden
sweep → weight manifest check).

### F8 — GPU sidecar trust boundary is implicit. LOW-MEDIUM.
`nemotron_server.py` accepts raw bytes on :8200 with no auth (compose
network + loopback publish — acceptable), transcodes via PIL (good — the
WebP fix also neutralized a decoder-reachability class), caps queue depth.
But it will decode arbitrary bytes with no size cap at ITS boundary (the
app enforces 8MB upstream; direct callers aren't bounded). **Fix:** size
cap + content sniff in `_ocr_sync`; document the sidecar as inside the
trust boundary, never internet-adjacent.

### F9 — AI RMF mapping is strong but unwritten. LOW.
The system embodies AI RMF MANAGE functions unusually well: human
decision primacy ("screening, never approval" enforced in code — VLM
suggestions cannot change status; agent override freezes fields), measured
error profiles per engine (the A/B sweeps), honest-degrade doctrine
(NEEDS_REVIEW over false verdicts, the thin-stroke/blur gates), calibration
telemetry (E4 + single_read flags), and provenance. What's missing is the
GOVERN artifact: a one-page AI risk statement mapping these mechanisms to
RMF functions for a reviewing office. **Fix:** distill this section +
PLAN-enrichment's hard rules into docs/ai-risk-statement.md. ~2 hours.

### F10 — 508 posture good, unverified. LOW.
Focus rings survived the restyle deliberately, aria-labels/pressed on all
decision controls, 44px+ targets, chips carry text not just color. Known
open item: focus restoration after re-render (tracked TODOS P2). No
screen-reader pass or VPAT exists. **Fix:** axe-core in CI (F1) + the
focus-restoration TODO + one manual NVDA/VoiceOver session before deploy.

## What's already strong (credit where the auditors will look)

- **EO 14028 supply chain:** `--require-hashes` install (1,119 hashes,
  PyPI-compromise resistant), SHA-256-pinned model weights asserted at
  build AND warm (drift caught live during development), scoped-source
  policy research with PRC-origin annotations ready for the SBOM.
- **No-egress runtime:** models baked at build; vendored CSS (no CDN);
  J4 cloud enrichment is flag-off + silent-degrade with payload logging
  designed in (AD-31) — the firewall story is a feature, not an accident.
- **Input hardening:** magic-byte image validation + MIME-from-content
  (stored-XSS guard in session store), 8MB/40MP caps, decompression-bomb
  ceiling, CSV formula guard (existing), TrustedHost middleware, per-IP
  token bucket + concurrency shed with Retry-After.
- **Least-privilege data design:** single-writer DuckDB documented;
  sessions loopback-only; secrets in gitignored .env, never echoed/logged.
- **Change control:** 114 conventional commits with review artifacts
  (/autoplan 45-decision record in-repo), tests at 159 passing, planted
  adversarial goldens as regression tripwires.

## Prioritized remediation roadmap

1. **F3 .dockerignore** (minutes; stops data-in-image today).
2. **F2 non-root containers** (~1 hour).
3. **F1 CI workflow** — tests, hash-install, integrity check, pip-audit,
   image scan, no-network suite, axe-core (~1 day; carries F7/F10 partway).
4. **F4 SBOM + attestation** in that workflow (~half day).
5. **F5 deploy security one-pager** — blocks the deployed URL P1 anyway.
6. **F6 log retention note + telemetry rotation** (~1 hour).
7. **F8 sidecar caps** (~30 min). 8. **F9 AI risk statement** (~2 hours).

FIPS 199 note for the record: Confidentiality MODERATE (pre-approval
commercial label data), Integrity MODERATE (verdicts feed federal review),
Availability LOW (batch tool, retry-tolerant) → the 800-53 moderate
baseline is the right control target for any deployed instance; the
FedRAMP-High/IL5 discussion applies only to the Gov-cloud escalation tier
already scoped in PLAN-us-stack.

---

## Re-audit — current implementation (2026-08-03 evening, suite 208 passed)

### Original findings: all ten verified CLOSED

| Finding | Status | Evidence in-tree |
|---|---|---|
| F1 CI pipeline | CLOSED | `.github/workflows/ci.yml` — hash-locked install, pytest, no-egress proof, pip-audit; weekly image job (build + non-root assert + no-data assert + trivy); axe job. First hosted run still awaits the user's push. |
| F2 root container | CLOSED | Dockerfile `USER app` (uid 1000); CI asserts `id -u` = 1000 |
| F3 data baked in images | CLOSED | `.dockerignore` (api/data, colacloud, batches, .env); CI asserts no-data paths absent in image |
| F4 SBOM/attestation | CLOSED | `scripts/gen_sbom.py` → `sbom/labelcheck.cdx.json` (71 components, licenses, PRC-origin annotations); regenerated this re-audit (R5) |
| F5 deploy security design | CLOSED | `docs/deploy-security.md` (TLS at edge, authn options, pre-flight checklist; DECIDE items remain the user's) |
| F6 log retention | CLOSED | E4 rotation at 20 MB (one generation); retention split documented (session store = system of record) |
| F7 dependency currency | CLOSED | monthly ritual documented; pip-audit advisory in CI; weekly image scan |
| F8 sidecar bounds | CLOSED | `nemotron_server.py` 12 MB cap + PIL transcode; documented inside-boundary |
| F9 AI risk statement | CLOSED | `docs/ai-risk-statement.md` (RMF GOVERN/MAP/MEASURE/MANAGE, residual risks owned) |
| F10 508 | CLOSED (process open) | axe in CI at 0 violations (re-verified after footer/subnav/tour changes); manual screen-reader session still a pre-deploy TODO |

### New surface since the audit, and findings

The tree gained: a UI telemetry endpoint, the guided walk-through +
runbook, a sticky filter sub-nav, commodity/status facets, three ingested
TTB anatomy reference sets + BAM fixtures, four new rules modules
(wine/malt additions), the earned-PASS gate, and ~50 commits of UI work.

**R1 · /api/telemetry shipped unmetered with an unbounded body. FIXED
same-day.** The endpoint (added for train-before-pilot T5) had the strict
event allowlist and numeric bounds from birth, but the per-IP token
bucket guarded only `/api/verify`, and `request.json()` would buffer an
arbitrarily large body. Fixed: same rate limiter + 429/Retry-After
contract, 1 KB content-length cap (413), tests pin both. Damage ceiling
even pre-fix was bounded by the 20 MB rotation and loopback-only posture
— but calibration-data dilution was a real risk. *Lesson recorded: every
new POST route must opt INTO the limiter explicitly; a middleware-level
default would fail safer (candidate for the deploy hardening pass).*

**R2 · Silent telemetry drops hid an hours-long data loss. FIXED
(detection), ops rule reaffirmed.** The E4 file was root-owned (written
by an early docker-compose run before the non-root fix); every native-
process write since morning was swallowed by the telemetry-never-breaks-
a-verdict guard — hours of J1 agreement rows (the N7 calibration input)
silently lost. The guard is correct and stays; what was missing is a
signal: `layers.telemetry_drops` now counts swallowed writes and
`/healthz` exposes it (`telemetry_drops`), tested. The root-owned file
was moved aside (`e4-telemetry.root-owned.bak`, local, gitignored —
harvest then delete). This is the standing DuckDB single-writer rule in
a new costume: **docker and native runs must not share api/data.**

**R3 · Committed third-party page snapshots. ACCEPTED with note.** Three
TTB tool pages (`api/eval/anatomy*/page.html`) are committed for
provenance. They are U.S. government works (public domain), live OUTSIDE
the `api/web` static mount (never served), and their external script/CSS
references are inert bytes in the repo. No action.

**R4 · Footer external links + runbook page. ACCEPTED.** All reference
anchors are user-initiated navigation with `rel="noopener"`; nothing
loads at page-load time; runbook.html uses only the vendored stylesheet.
The no-egress runtime claim is unchanged and the CI no-egress proof
still passes.

**R5 · SBOM metadata staleness. FIXED.** `requirements.lock` is unchanged
since generation, so component contents were accurate, but the embedded
commit hash was stale. Regenerated at the current tree (71 components,
68 licensed, 8 origin-annotated). The release ritual (F7) covers this
going forward.

**R6 · Client-side-only enforcement of the earned-PASS gate. NOTED,
deploy-gated.** The whole-label PASS lock (`passBlockers`) is a UI
control; decisions live client-side until session save, so this is
consistent today. If the deployed-URL work adds a server decision
endpoint, the same predicate must be mirrored server-side (AD-27
server-side-terminality) — added to the deploy checklist expectations.

Reviewed with no findings: tour engine (innerHTML paths escape via
`esc()`; no user-controlled strings reach the tooltip), training-set
metadata (server-controlled), locator changes (parsing only), new rules
modules (pure functions, no I/O), commodity/status facets (no input
surface), footer `data-act` handlers (allowlisted actions).

### Scorecard (refreshed)

| Area | Was | Now | Basis |
|---|---|---|---|
| Supply chain (800-161, EO 14028) | B+ | **A-** | SBOM shipped + regenerated; locks + weight pins; CI proves the lock per-push |
| Secure development (SSDF 800-218) | C+ | **B+** | CI gates on every push (pending first hosted run); tests 208 |
| Container security (800-190) | C- | **B** | non-root asserted in CI; no-data asserted; base tags still mutable (accepted for a prototype) |
| Access control / network (AC/SC) | B- | **B-** | unchanged by design — deploy-gated (docs/deploy-security.md) |
| Audit & accountability (AU) | B | **B+** | provenance + rotation + drop-counter health signal |
| AI risk (AI RMF 1.0) | B+ | **A-** | risk statement artifact; decision friction now ENFORCED (earned-PASS); tour teaches the no-authority posture |
| Accessibility (508) | B | **B+** | axe 0 violations in CI, re-verified after every UI change; manual session still open |

Standing user-action items unchanged: push to origin (gives CI its first
run), deploy-security DECIDE items, one manual screen-reader session,
harvest-and-delete the root-owned telemetry backup.
