# Label Check — TTB Label Screening Assistant

A prototype that verifies alcohol beverage label images against COLA application
data — brand name, class/type, alcohol content, net contents, and the statutory
Government Warning — in about **2 seconds per label**, entirely on infrastructure
you control. Built for the [Treasury take-home exercise](docs/assignment-brief.md).

**It screens; the agent decides.** The tool never approves anything — its
all-clear state reads *"ready for agent sign-off"*, every verdict shows the image
region it was read from, and the agent can override any result (overrides are
audited in the export).

## Run it

```bash
docker compose up          # then open http://localhost:8123
```

First boot downloads OCR models (~30MB) and warms them; `/healthz` reports
`ready` when the app will answer in ~2s. **Requires ~4GB of memory for Docker**
(exit code 137 during warmup = raise Docker's memory limit).

No API keys. No outbound ML calls — **verified**: the container boots to ready
and returns correct verdicts with networking removed entirely
(`docker run --network none labelcheck`). The same 1.83GB image runs on a
laptop, a cloud VM, or inside TTB's firewall unchanged — that *is* the
architecture's answer to the prior vendor pilot that died on blocked ML
endpoints. (Finding the offline path even caught an upstream bug: paddlex
phones home at model init unless local model dirs are explicit — baked and
pinned in the Dockerfile.)

<details><summary>Local dev without Docker</summary>

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r api/requirements.txt fastapi uvicorn python-multipart
make serve        # http://localhost:8123
make test         # 35 unit tests, no OCR needed, <1s
make eval         # M0 golden-set fidelity + latency report
make smoke        # end-to-end: clean sample must go all-green in <5s
```
(paddle is pinned to 3.2.2 — 3.3.x has a CPU inference bug.)
</details>

## Try these five samples (built into the UI)

1. **Clean match** — the all-clear state, end to end in ~2s.
2. **Obvious mismatch** — label prints 46% against a 45% application (outside the ±0.3 regulatory band).
3. **Title-case warning trap** — the check Jenny caught by eye: `Government Warning`
   in title case. Vision-language models tend to autocorrect this back to caps;
   local OCR reads what's printed, so this prototype catches it — with a
   word-level diff in plain English.
4. **Bad photo** — degrades honestly to NEEDS REVIEW with actionable copy; never a false verdict.
5. **Table wine with no ABV** — legally compliant (27 CFR §4.36(a)) → **NOT REQUIRED**, not a mismatch.

Or poke the API directly (`/docs` for Swagger):

```bash
curl -F "image=@api/eval/golden/spirits_clean.jpg" \
     -F 'application={"beverage_type":"distilled_spirits","brand_name":"OLD TOM DISTILLERY","class_type":"Kentucky Straight Bourbon Whiskey","alcohol_content":"45% Alc./Vol.","net_contents":"750 mL"}' \
     http://localhost:8123/api/verify
```

## Architecture, in six lines

```
BROWSER (static page; evidence crops rendered client-side from bbox coordinates)
   │ multipart image + application JSON
   ▼
FASTAPI ─▶ validate (type/size/40MP, EXIF) ─▶ PaddleOCR (local, warmed, locked)
   ▼                                              words + boxes + confidences
LOCATOR (reading order, cross-line windows, ambiguity margin, warning-block reconstruction)
   ▼
RULES ENGINE (pure functions, cited) ─▶ verdicts: MATCH / LIKELY MATCH / WITHIN
TOLERANCE / MISMATCH / NEEDS REVIEW(reason) / NOT CHECKED / NOT REQUIRED
```

**Why the model never decides:** compliance verdicts come from a deterministic,
unit-tested rules engine over *verbatim* OCR text. OCR preserves case and
misspellings by construction — which is exactly what a statutory exact-match
check needs. The one legal formatting rule a photo can't reliably prove (bold
weight) is measured conservatively: equal-weight never reads "ok", ambiguity
degrades to *"confirm visually"* (that property is an executable test).

**Regulatory depth where it counts:** ABV uses a three-band model — exact match
is green; a difference inside the commodity's band (wine ±1.0/±1.5, spirits and
malt ±0.3, per 27 CFR §§4.36/5.65(c)/7.65(c)) is **amber "confirm", never
green** (the CFR tolerances govern label-vs-actual product, so the warrant for
tolerating drift is Form 5100.31's allowable-revision item 11 — both cited in
the UI); outside the band, or across a class boundary (14/21/24% wine, 2.5%
"low alcohol", 0.5% "non-alcoholic"), is red with no tolerance rescue. Missing
ABV is commodity-aware: optional on ≤14% "table"/"light" wine and unflavored
malt → **NOT REQUIRED** with its citation, not a false mismatch.

## Measured, not asserted

On a 16-core CPU dev box (no GPU), against the 15-label golden set:

| Metric | Value |
|---|---|
| End-to-end verify (API, warm) | **~2.0-2.4s** |
| OCR-only p50 / p95 / max | 2.19s / 2.65s / 2.78s |
| Cold start (model init + warmup) | ~14s, gated behind `/healthz` |
| Field location rate (incl. degraded photos) | 94.8% |
| Title-case caps trap discriminated on raw OCR | yes |
| 5-label concurrent batch wall-clock | 11.1s (serialized single instance) |
| Real-label corpus (8 Napa wine photos) p50 | 2.82s; **0 false mismatches**, uncertainty → review w/ crops |
| Unit tests | 38, <1s, no OCR required |

Raw artifacts: [`api/eval/results/`](api/eval/results/). Beyond the synthetic
golden set, a second corpus of **real Napa/California wine label photographs**
(Wikimedia Commons, CC-licensed, provenance per image in
[`api/eval/napa/manifest.json`](api/eval/napa/manifest.json)) exercises script
fonts, occlusion, low-res, two-bottle frames, and — on a real Stag's Leap
"Red Table Wine" label — the live §4.36(a) NOT-REQUIRED path (`make eval-napa`).
A third source is on tap: `make eval-pull-colacloud` (with a
`COLACLOUD_API_KEY` from [app.colacloud.us](https://app.colacloud.us)) pulls
**approved COLAs from the public registry** per commodity — wine, beer,
spirits — using the registry record itself as application ground truth; pulled
sets auto-register as one-click eval sets in the UI. The CI-style gates are
executable: `make smoke` fails if the clean sample isn't all-green within 5s.

Batch today serializes on one warmed OCR instance (~2.2s/label → 300 labels
≈ 11 min); the measured worker-pool scale-up (2 processes ≈ half that) is
specified in [PLAN.md](PLAN.md) and is deliberately not shipped un-measured.

## What's deliberately out (and where that's written down)

Single image per label (real filings upload each panel separately — the top
deferred item), standards of fill/appellations/age statements, COLA
integration, auth/persistence, type-size and placement rules (physical-scale
checks a photo can't prove — each labeled "not checked" with its §16.22
citation in the UI). Full ledger: [TODOS.md](TODOS.md); every scope decision
with rationale: [PLAN.md](PLAN.md) (38-decision audit trail).

## How this was built (the paper trail)

- **[PLAN.md](PLAN.md)** — the implementation contract: reviewed by a
  four-phase dual-model pipeline (Claude + GPT voices), revised against
  primary-source regulatory research, 38 logged decisions, zero unresolved.
- **[docs/research/](docs/research/)** — 14 studies: eCFR labeling rules,
  a 100-point COLA fact sheet, the pre-screening market, failure modes and
  success playbooks for government modernization/AI/OCR, and the Treasury +
  national AI strategies this prototype aligns with (Treasury's own AI
  strategy names "document processing and regulatory intake" as a priority
  use case — and TTB's FAQ concedes reviewer consistency "can be addressed
  only to a limited degree by a Web-based system," which is precisely the
  gap deterministic, citation-backed checks close).
- **[docs/reviews/](docs/reviews/)** — comparisons against seven public
  solutions to this exercise; the adopted ideas (reviewer override, TTB's own
  label-examples guide as ground truth, CI latency assertion, end-to-end
  reachability tests) are credited inline.

## Assumptions & trade-offs (summary)

Application data is agent-entered (no COLA feed); one image per label
(stated in-UI); English labels; bold-weight measurement is conservative by
contract; results live only in the browser tab (stateless server, nothing
stored); public-demo hardening (rate limiting, per-IP caps) is specified in
PLAN.md but not enabled by default in the local build. The honest failure
mode everywhere is **NEEDS REVIEW with a reason and a crop** — never a
confident wrong answer.
