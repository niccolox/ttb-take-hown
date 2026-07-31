# Top 10 Reasons Government AI Projects Fail

Researched 2026-07-31. Sources: GAO's AI-acquisition audit series, federal pilot-to-production analyses, and the two landmark algorithmic-government failures (Australia's Robodebt, the Dutch childcare-benefits scandal). Companion to `gov-modernization-failure-modes.md` (institutional failure) and `ocr-project-failure-modes.md` (system-layer failure); a closing table maps each mode to this repo's PLAN.md.

The headline number: **80-90% of government AI pilots never reach production**, with some analyses putting the no-measurable-value rate at 95% ([Alpha Omega](https://alphaomega.com/blog/ai/ai-pilots-federal-government-production/), [Truvisory](https://truvisory.com/federal/why-federal-ai-pilots-stall/)).

---

## 1. The pilot-to-production chasm

Pilots run on curated datasets "cleaned, labeled, and structured specifically for the proof-of-concept"; production runs on the real intake. The demo proves the model works on the data that was prepared for it — a different claim from the one the agency needs ([Alpha Omega](https://alphaomega.com/blog/ai/ai-pilots-federal-government-production/), [FedScoop](https://fedscoop.com/federal-agencies-ai-operational-integration-outcomes/)). This is the AI-specific form of the OCR benchmark-vs-corpus trap.

## 2. No quantified mission value

"Pilots demonstrate technical abilities but often fail to quantify business value" — without metrics on cost, efficiency, or mission impact, nobody can justify enterprise deployment, and the pilot dies in permanent-demo purgatory ([Alpha Omega](https://alphaomega.com/blog/ai/ai-pilots-federal-government-production/), [4points](https://www.4points.com/blog/fed-ai-initiatives/)). The unmeasured pilot is indistinguishable from a failed one.

## 3. Procurement built for a different cadence

GAO's six AI-acquisition challenge areas include "traditional acquisition time frames and contract approaches" — FAR-based awards can take **two years**, an eternity against model release cycles ([GAO-26-107859](https://files.gao.gov/reports/GAO-26-107859/index.html), [ExecutiveGov](https://www.executivegov.com/articles/gao-report-ai-procurement-challenges-federal-agencies), [Biometric Update](https://www.biometricupdate.com/202604/gao-warns-federal-ai-procurement-is-repeating-the-same-mistakes)). Contracts also routinely fumble "requirements definition and contract terms" and "AI pricing" — GAO's programmatic triad.

## 4. Data readiness and data rights unsettled

The second GAO strategic challenge: "protections for government data and intellectual property rights." Agencies discover mid-project that the training/inference data is dirty, siloed, legally encumbered, or that the vendor's terms give away more than the agency can lawfully give ([GAO-26-107859](https://files.gao.gov/reports/GAO-26-107859/index.html)).

## 5. Skills gap and contractor dependency

"Successful pilots can depend on contractors or specialized AI researchers who move on," while production needs sustained monitoring, retraining, and incident response the agency can't staff ([Alpha Omega](https://alphaomega.com/blog/ai/ai-pilots-federal-government-production/)); GAO lists "access to subject matter experts" as challenge #1. The system outlives the team that understood it.

## 6. No early testing or continuous evaluation

GAO's third programmatic challenge: "early testing and continuous evaluation" — AI behavior shifts with inputs, model updates, and drift, yet projects ship with launch-day validation only ([GAO-26-107859](https://files.gao.gov/reports/GAO-26-107859/index.html), [gov.appmaisters](https://gov.appmaisters.com/how-government-agencies-can-overcome-the-challenges-of-ai-pilots/)). Without a standing eval harness, nobody can even say whether the system still works.

## 7. Automating judgment without legal authority — and removing the humans

**Robodebt**: income averaging that was "no way to accurately calculate fortnightly pay" ran for years as human oversight was "progressively removed," pursued "without regard for legal authority, ethical safeguards, or the basic dignity of the people affected" — a royal commission, ~A$1.8B in remediation, officials fined and demoted. The failure wasn't the math being crude; it was crude math being given decision authority over people with the appeal path dismantled.

## 8. Bias in, accountability out

**The Dutch childcare-benefits scandal**: a risk-profiling algorithm treated dual nationality as a fraud signal; ~35,000 families — mostly migrants — were wrongly accused across six years "with no human oversight to catch these errors," and the fallout brought down the Rutte cabinet in 2021 ([EU Law Enforcement](https://eulawenforcement.com/?p=7941), [CIPP retrospective](https://cipptraining.com/the-dutch-ai-scandal-a-cautionary-tale-of-automated-injustice-2025/), [comparative review](https://www.researchgate.net/publication/376695073_Lessons_to_Be_Learned_from_the_Dutch_Childcare_Allowance_Scandal_A_Comparative_Review_of_Algorithmic_Governance_by_Tax_Administrations_in_the_Netherlands_France_and_Germany)). Government AI failures are not IT failures; they are legitimacy failures with political half-lives measured in decades.

## 9. Opacity kills trust — for citizens and for staff

Even good-faith efforts founder here: Amsterdam's deliberately "fair" welfare-fraud model — bias-audited, consulted, transparent by design — still couldn't produce outcomes the city would defend, and was shut down ([MIT Technology Review](https://www.technologyreview.com/2025/06/11/1118233/amsterdam-fair-welfare-ai-discriminatory-algorithms-failure/), [Lighthouse Reports](https://www.lighthousereports.com/investigation/the-limits-of-ethical-ai/)). Citizens attribute discriminatory outcomes differently when an algorithm decides ([JPART study](https://academic.oup.com/jpart/article/35/4/469/8249873)); staff who can't see *why* the system flagged something either rubber-stamp it (Robodebt) or route around it (adoption death). Explainability and contestability are load-bearing, not compliance garnish.

## 10. No lessons-learned loop — the same mistakes, re-procured

GAO's title finding: agencies "should collect and apply lessons learned" — officials at four agencies weren't prepared to collect them at all because no policy required it, so each procurement repeats the last one's mistakes ([GAO-26-107859](https://files.gao.gov/reports/GAO-26-107859/index.html), [Biometric Update](https://www.biometricupdate.com/202604/gao-warns-federal-ai-procurement-is-repeating-the-same-mistakes)). The institutional memory that engineering retrospectives provide simply doesn't exist in the acquisition cycle.

---

## Mapping to this project

| # | Failure mode | PLAN.md answer |
|---|---|---|
| 1 | Pilot-to-production chasm | M0 calibration corpus includes real photos + real COLA images (adopted); deployed demo runs the same Docker image as on-prem — the pilot *is* the production artifact |
| 2 | Unquantified value | Measured p50/p95 published; verdict distributions; time-per-label vs Sarah's 5-10 min baseline is the stated value metric |
| 3 | Procurement cadence | Open-stack, keyless, `docker compose up` — the anti-procurement demo; Extractor interface keeps vendor choices reversible |
| 4 | Data readiness/rights | No PII stored, log redaction, statutory text with provenance; fixtures carry licensing notes (adopted from competitor survey) |
| 5 | Skills/contractor dependency | Boring, documented stack (FastAPI + PaddleOCR); README/runbook as deliverables; no model training to sustain |
| 6 | No continuous eval | M0 spike becomes the permanent eval harness; snapshot-pinned goldens; CI latency + reachability assertions |
| 7 | Judgment without authority | The rules engine never approves — "ready for agent sign-off" framing; LIKELY MATCH and NEEDS REVIEW route to humans; reviewer-override with audit columns (TODO) |
| 8 | Bias in, accountability out | Deterministic rules are inspectable; no risk scoring of *people* anywhere in the design; per-field regulatory citations (TODO) |
| 9 | Opacity | Evidence crops, preprocessing audit trail, word-level diffs, reason codes — every verdict shows its work |
| 10 | No lessons loop | This docs/ tree: review records, decision audit trail, competitor survey, failure-mode research — the lessons file exists before the code does |

The three research docs triangulate the same conclusion from different altitudes: modernization projects fail institutionally, OCR projects fail at the system layer, and AI projects fail at the *authority* layer — who decides, who checks, who answers when it's wrong. The plan's one-sentence defense against all three: **the model never decides, the human always can, and every claim is measured.**
