# AI Risk Statement — NIST AI RMF 1.0 Mapping (audit F9)

One page for a reviewing office: what this system is, what AI risk it
carries, and which SHIPPED mechanisms manage that risk. Everything cited
is implemented and tested in this repository — nothing aspirational.

**System:** Label Check screens alcohol-label images against COLA
application data using local OCR engines, a rules engine with CFR
citations, and optional assistive models. **It is a screening aid with no
approval authority — every disposition is a human agent's decision.**

## GOVERN — accountability structures

- Human decision primacy is enforced IN CODE, not policy prose: assistive
  model output (VLM suggestions) cannot change a field status
  (`test_j3_attaches_suggestion_without_status_change`); an agent's
  decision freezes the field against machine mutation (precedence rule:
  agent override > settled verdict > provisional); whole-label sign-off
  is the agent's, recorded with timestamp and the original machine state.
- Every verdict change carries provenance (layer, engine, from → to,
  applied?) in the result payload — the audit trail is part of the data
  model, not a log format.
- Plans of record: PLAN.md (ratified premises incl. no-cloud-ML),
  PLAN-enrichment.md (45 reviewed decisions, AD-1..AD-40).

## MAP — context and known limits

- Measured, published error profiles per engine (docs/research/
  removing-paddle-nemotron-only.md): each engine's blind spots are known
  from golden-corpus A/B sweeps, not assumed.
- Known limits are encoded as honest outcomes: statutory-text comparison
  is exact-only; weight-contrast declines to judge below its measured
  resolution floor (thin-stroke and blur gates); unreadable degrades to
  NEEDS_REVIEW with evidence crops — never a fabricated verdict.
- Input domain is bounded: image formats/size/pixel caps, no free-text
  prompts anywhere in the verdict path.

## MEASURE — evaluation and calibration

- Golden corpora with planted adversarial cases (title-case, all-bold,
  word-substitution, ABV-band traps, degradations) run as regression
  tripwires; 159 automated tests in CI.
- Dual-engine QA (J1) records per-field agreement telemetry (E4 stream,
  incl. single-read flags) — the standing calibration dataset; per-engine
  confidence floors are explicit and scheduled for recalibration (N7).
- Determinism is an exit criterion (same image → same settled verdict,
  3/3), verified on the corpus.

## MANAGE — response to identified risk

- Disagreement between engines on statutory/numeric fields locks the
  field for the human with BOTH reads shown — conflict is surfaced,
  never averaged away.
- Degradation doctrine: every uncertain path lands on NEEDS_REVIEW with
  the evidence crop; false-red and false-green classes found in testing
  were fixed at the measurement layer (region clipping, blur gate) and
  pinned with tests.
- Cloud AI is off by default and fails silent-closed (byte-identical
  behavior offline, proven in the no-egress check); the only hosted-model
  path (VLM assist) is crops-only, suggestion-only, disclaimer-labeled.
- Supply chain: hash-locked dependencies, SHA-256-pinned model weights
  asserted at build and startup, SBOM with origin annotations
  (sbom/labelcheck.cdx.json).

## Residual risks (stated, owned)

1. OCR misreads within confidence bounds can survive to a green verdict;
   mitigated by dual-engine guard on the highest-consequence fields and
   the agent's evidence crops — not eliminated.
2. Automation bias: a polished green verdict invites rubber-stamping;
   mitigated by amber-first UI language, withheld provisional verdicts,
   and per-field decision friction — monitored via decision telemetry.
3. Engine model drift on upgrade; mitigated by the pinning + golden-sweep
   ritual (docs/deploy-security.md).
