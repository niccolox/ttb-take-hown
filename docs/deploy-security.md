# Deployed-URL Security Design (one page — audit F5)

This page is the precondition the enrichment plan's AD-31 already imposes:
"result endpoints inherit the deployed-URL work's auth and are blocked from
deploy until it exists." Nothing below is aspirational except where marked
DECIDE — those are the choices the deploy engineer confirms before the
first public byte.

FIPS 199 categorization (from the DevSecOps audit): Confidentiality
MODERATE (pre-approval commercial label data), Integrity MODERATE,
Availability LOW → 800-53 moderate baseline.

## Network + transport

- TLS terminates at the PLATFORM edge (App Service/ACA managed cert or a
  reverse proxy with ACME). The app itself stays plain HTTP on loopback /
  the container network — no TLS code in-app, ever.
- `LABELCHECK_ALLOWED_HOSTS` MUST be set to the public hostname(s); the
  default loopback allowlist refuses everything else (TrustedHost, AD-31).
- The GPU sidecar (:8200) and any future J-layer service bind only to the
  container network — never a public listener. The sidecar bounds its own
  inputs (12MB cap, PIL transcode) but is designed as inside-boundary.

## Authentication (DECIDE one before deploy)

The app is deliberately auth-less; auth is a fronting concern:
1. **Entra ID / OAuth2 at a reverse proxy** (oauth2-proxy or platform
   auth) — the pragmatic choice for a demo URL; per-user identity lands in
   headers the app can log alongside agent decisions.
2. **PIV/CAC via agency SSO** — the Treasury-native answer if this ever
   fronts real reviewers; same proxy pattern, different IdP.
No third option: an unauthenticated public URL never ships — the
take-home demo can use a long random path + IP allowlist ONLY if a
reviewer explicitly accepts that in writing.

## In-app posture at exposure time

- Rate limits reviewed: default 30 rpm/IP is tuned for one reviewer, not
  a shared NAT — raise deliberately (`LABELCHECK_RATE_RPM`), keep the
  429/Retry-After contract.
- `LABELCHECK_JOBS`/J4 flags: cloud enrichment stays OFF on any instance
  holding real pre-approval data (D3's silent-degrade covers outages, not
  policy).
- Session store: `api/data` volume on encrypted storage (platform default
  on Azure managed disks); it contains reviewed label images.
- Startup refusal (AD-31, implemented as the allowlist default): binding
  non-loopback without the hostname allowlist set is a misconfiguration,
  not a working state.

## Logging & retention (audit F6)

- System of record for DECISIONS = the session store (agent overrides
  carry timestamps + originals; refinement provenance rides each result).
- E4 telemetry rotates at 20MB (one generation kept) — calibration data,
  not an audit log.
- Platform log driver owns transport/access logs; retention per Treasury
  records schedule (default: 90 days hot is sufficient for a prototype;
  DECIDE with the records officer before production).

## Dependency currency ritual (audit F7)

Monthly, or on any relevant advisory: regenerate the lock
(`uv pip compile api/requirements.in --generate-hashes`), run the suite +
golden sweep, re-run `python -m api.integrity check` (a paddle bump MUST
regenerate api/models.sha256 in the same commit), regenerate the SBOM
(`scripts/gen_sbom.py`). CI's weekly image job + pip-audit is the
between-rituals tripwire.

## Pre-flight checklist (the day of)

- [ ] TLS at edge, HTTP internally, hostname in LABELCHECK_ALLOWED_HOSTS
- [ ] Auth proxy in front (option 1 or 2 above), verified with a 401 curl
- [ ] Rate limits set for expected concurrency
- [ ] J4/cloud flags off; `.env` provisioned server-side, never in image
- [ ] `api/data` on encrypted, backed-up storage
- [ ] Image built by CI (non-root + no-data assertions green), not a laptop
- [ ] Smoke + no-egress check green against the deployed instance
