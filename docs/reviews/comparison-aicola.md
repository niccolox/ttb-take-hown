# Comparison: our PLAN.md vs treasurymike/aicola

Cloned to `comparisons/aicola` (2026-07-31). Tiny footprint: 4 Java files (Spring Boot 3.5, Anthropic Java SDK) + 1 Next.js page, ~364KB, no tests. Live on Railway. Notably: this is a faithful build of **our original Approach A** — the cloud vision-LLM architecture reversed at our premise gate — so it works as a natural experiment for that road-not-taken.

## Their shape

- One Claude vision call per label (front + optional back image) with a structured-output schema forcing a verdict per requirement; `claude-haiku-4-5` default, `claude-opus-4-8` + adaptive thinking as the thorough option.
- 8 requirement checks (brand, class/type, ABV, name/address, net contents, country of origin, warning, commodity disclosures) with commodity-aware prompting — including a wine front-label placement rule.
- Deterministic post-checks only for the warning regex and normalized brand/net-contents comparison; everything else (presence, issues, form-to-label consistency) is **model judgment**.
- Batch = "+ Add another label", parallel browser requests; README concedes it's for tens, not the 200-300 scenario.
- API key passthrough: caller can supply their own key per request via header.
- Firewall answer: deploy note proposing Claude via **Microsoft Foundry inside Azure** — no firewall exception needed.

## Where they're strong

1. **Front + back label support out of the box** — our multi-image handling is a deferred P2 TODO, and they're right that real bottles need it (their `foundOn: front|back|both` field is a clean schema idea).
2. **Broader rule surface**: name/address, country-of-origin (imports), commodity-specific disclosures (sulfites, FD&C Yellow No. 5), and the wine placement rule — more of 27 CFR covered than our four core fields, albeit via prompt rather than code.
3. **The Foundry answer to Marcus's firewall** is genuinely clever procurement thinking: keep the cloud model but serve it from inside Azure. It's the strongest version of the cloud architecture's defense.
4. **Honest README**: admits the 5s target is "only partially met" and batch doesn't reach 300; assumptions and limitations are well-documented.
5. Sensible small touches: client downscale to 1600px, per-label commodity settings inherited by the next label, batch results streaming as they complete.

## Where the road-not-taken shows its cost (validating the premise-gate pivot)

1. **Latency: 5-15s per label, self-admitted.** The one requirement the README calls a hard adoption threshold ("If we can't get results back in about 5 seconds, nobody's going to use it") is missed by the architecture itself — network + frontier-model inference has a floor that local CPU OCR doesn't. Our plan treats 5s as a measured M0 gate; theirs documents the miss as a limitation.
2. **The caps check rests on LLM transcription fidelity.** Their warning regex is `CASE_INSENSITIVE`; the all-caps check is just `extractedText.contains("GOVERNMENT WARNING")` — which only works if the model transcribed case faithfully. Vision LLMs autocorrect toward the statutory text they've memorized (the exact critical finding from our Phase 1 CEO voice), so a title-case label plausibly comes back transcribed as all-caps and **passes**. Bold is never checked at all — it's lumped into the same error message. OCR-based pipelines get case verbatim by construction; this is the trap the cloud architecture can't fully escape.
3. **The LLM decides most verdicts.** Presence, issues, and the form-to-label MATCH/MISMATCH table are model judgment (`consistent=true only if the label genuinely agrees` — a prompt, not a rule); only brand/net-contents get a deterministic comparison. Our spine — the model never decides compliance — is the auditable posture; theirs is auditable for two fields.
4. **No evidence provenance.** No crops, no bounding boxes, no way for an agent to see *where* a value was read — verdicts are assertions. Both our outside voices called visual provenance the highest-trust feature.
5. **No confidence architecture.** The model self-reports high/medium/low; there's no gate routing low confidence to a NEEDS REVIEW state (their statuses are PASS/WARN/FAIL only), so "never a false PASS" has no mechanism.
6. **Zero tests.** No unit tests, no golden set, no eval harness — the two deterministic checks are the only inspectable logic, and nothing exercises them.
7. **Public server key exposure**: with no rate limiting visible, the deployed demo's fallback `ANTHROPIC_API_KEY` is spendable by anyone who finds the endpoint (the key-passthrough option mitigates but doesn't gate the default path).
8. **DX**: two terminals, JDK 21 + Maven + Node + an API key as prerequisites, no Docker, no single-command path — heavier evaluator setup than either our plan (compose pull) or the other competitor's scripts.

## Three-way picture (aicola vs ttb-label-reviewer vs our plan)

| | aicola (cloud LLM) | ttb-label-reviewer (local OCR, 41k LOC) | our PLAN.md |
|---|---|---|---|
| 5s requirement | 5-15s, admitted miss | 4.15s median — on an RTX 4090 | M0 measurement gate on target CPU, fallback ladder |
| Warning caps trap | Rests on LLM case fidelity | Missed (`.upper()` both sides) | Case-sensitive prefix sub-check on raw OCR |
| Decision authority | Mostly model | Deterministic rules | Deterministic rules |
| Evidence | None | Crops (+ fake "estimated" fallback) | Crops, honest fallback |
| Multi-image | Yes (front+back) | Single | Deferred (TODO P2) |
| Rule breadth | 8 requirements, commodity-aware | Deep class/type domain tables | 4 core + warning, type-aware deferred |
| Tests | None | ~240 tests + golden set | Planned: units + golden + eval gates |
| Firewall story | Foundry-in-Azure proposal | Local by construction | Local by construction |

## Adopt from them

- `foundOn: front|back|both` schema shape when the multi-image TODO lands.
- Commodity-aware placement rules (wine front-label rule) as part of the beverage-type checklist TODO.
- The Foundry-in-Azure note as the documented *cloud-assist* variant behind our `Extractor` interface (upgrades the on-prem VLM TODO with a second compliant option).
- Batch UX touch: new label inherits the previous label's settings.
