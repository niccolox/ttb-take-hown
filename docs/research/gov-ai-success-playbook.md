# Top 10 Success Strategies, Tactics, and Operations for Government AI

Researched 2026-07-31. The inverse of `gov-ai-failure-modes.md`: what the agencies that *succeed* actually do, drawn from the OMB M-24-10 governance regime, the NIST AI RMF playbook, and the deployments with published numbers (IRS, VA, Treasury, CMS). Grouped as the practitioner would run them: **strategy** (what to decide), **tactics** (what to build), **operations** (what to run). A closing table maps each to this repo's PLAN.md.

The proof such numbers exist: VA's Automated Decision Support cut average claims processing **from 141 days to 81 (-42%)** and pushed the backlog below 100,000 for the first time since 2020; VA GPT's 95,000 users report saving 2-3 hours/week ([FedTech](https://fedtechmagazine.com/article/2026/05/amid-historic-staffing-lows-ai-augments-federal-workers)).

---

## Strategy

### 1. Start small on a discrete, high-volume, measurable process

The winning pilots target "discrete mission-support processes — backlog reduction in IRS audits, chatbot triage for VA users, contract-solicitation review at GSA" — where real usage data and metrics accumulate fast ([ICF](https://www.icf.com/insights/analytics/ai-government-use-cases)). Pick the process where volume is high, judgment is routine, and the baseline is quantified — then the value case writes itself (VA: 141→81 days). Boiling-the-mission is how pilots die; boiling one queue is how they scale.

### 2. Augment the workforce, don't replace the judgment

The through-line of every working federal deployment: AI drafts, flags, ranks, and summarizes; humans decide. IRS's fraud tooling "assesses the output of multiple machine-learning models to flag possible fraud, which is then reviewed by a human"; CMS built a "fraud war room" pairing model output with legal counsel, OIG, and investigators on the highest-risk cases ([FedTech](https://fedtechmagazine.com/article/2026/05/amid-historic-staffing-lows-ai-augments-federal-workers)). Framed this way, the workforce adopts the tool instead of fighting it — the exact inverse of Robodebt.

### 3. Fix the foundations before the flourish

"The agencies seeing results share a key trait: they did the unglamorous work before deploying anything" ([FedTech](https://fedtechmagazine.com/article/2026/05/amid-historic-staffing-lows-ai-augments-federal-workers)). The IRS invested in code translation to modernize legacy systems *before* layering AI on top; Treasury scaled through a deliberately human-centered enablement program rather than tool-first rollout ([AWS Public Sector on Treasury](https://aws.amazon.com/blogs/publicsector/how-the-u-s-department-of-the-treasury-is-using-a-human-centered-approach-to-scale-ai-innovation/)). Data plumbing, identity, logging, and eval infrastructure are the project.

### 4. Adopt the governance frame before it's imposed

OMB M-24-10 makes inventories, risk rating, and minimum practices for rights- and safety-impacting AI mandatory ([M-24-10 overview](https://digitalgovernmenthub.org/examples/omb-m-24-10-advancing-governance-innovation-and-risk-management-for-agency-use-of-artificial-intelligence/), [Regulations.AI](https://regulations.ai/regulations/RAI-US-NA-OMMAGXX-2024)); NIST's AI RMF playbook operationalizes it through Govern/Map/Measure/Manage ([NIST AI RMF Playbook](https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-rmf-playbook)). Successful teams treat these as design inputs on day one — projects that bolt governance on later re-architect under audit.

## Tactics

### 5. Confidence thresholds route work; they don't approve it

The IRS pattern: model confidence determines *routing* — high-confidence cases move fast, low-confidence cases queue for humans — never final disposition ([FedTech](https://fedtechmagazine.com/article/2026/05/amid-historic-staffing-lows-ai-augments-federal-workers)). This converts imperfect models into perfect triage: the error budget lands on human desks instead of citizens' records.

### 6. Ship the safeguards as features: redaction, audit logs, provenance

Working systems "incorporate safeguards such as PII redaction, audit logs, and human-in-the-loop review" as first-class capabilities ([SmartDev federal use cases](https://smartdev.com/ai-use-cases-in-federal-government/)). Audit trails and explainable outputs aren't compliance tax — they're what lets counsel, IGs, and appeal processes say yes.

### 7. Templates, model cards, and role-based enablement

The M-24-10 implementation playbook: define governance artifacts early (AIA templates, model-card schemas, intake forms capturing data provenance and citizen impact), and train by role — acquisition officers get procurement templates, program managers get impact-assessment literacy, engineers get RMF-grade model risk practice ([Rose Digital implementation guide](https://builtbyrose.co/omb-m-24-10-ai-governance-implementation-guide/)). Artifacts scale expertise the team doesn't have headcount for.

## Operations

### 8. Inventory, register, and publish — in the first 90 days

The realistic 90-day plan: stand up the use-case registry, complete the inventory, rate risk, identify high-risk systems for prioritized review, publish mitigation summaries ([Rose Digital](https://builtbyrose.co/omb-m-24-10-ai-governance-implementation-guide/), [Carahsoft compliance plans](https://static.carahsoft.com/concrete/files/2317/3888/1325/Compliance_Federal_Agency_AI_OMB_M-24-10_Compliance_Plans.pdf)). What's registered can be governed; what's shadow-IT becomes next year's scandal.

### 9. Monitor for drift as an operating function, not an afterthought

Deploy "monitoring hooks for performance and drift" as part of go-live ([Rose Digital](https://builtbyrose.co/omb-m-24-10-ai-governance-implementation-guide/)); NIST's Measure/Manage functions make continuous evaluation a standing operation ([EFROS RMF guide](https://efros.com/resources/nist-ai-rmf-implementation-guide/)). The 2024 federal AI inventory shows the trajectory — 1,700+ registered use cases and climbing ([inventory analysis](https://www.ictworks.org/wp-content/uploads/2026/03/US-Federal-AI-Inventory-Analysis.pdf)) — the ones that survive are the ones somebody is watching.

### 10. Publish the numbers — adoption compounds on proof

VA publishes 141→81 days; VA GPT publishes hours-saved-per-user; IRS publishes its use-case inventory and governance policy ([IRM 10.24.1](https://www.irs.gov/irm/part10/irm_10-024-001r), [FedScoop](https://fedscoop.com/treasury-irs-ai-use-case-inventory/)). Published, honest metrics do triple duty: they defend the budget, recruit the next office, and discipline the team against demo-ware claims. Success in government AI is a *communications* operation as much as a technical one.

---

## Mapping to this project

| # | Success practice | PLAN.md implementation |
|---|---|---|
| 1 | Start small, measurable, high-volume | One queue (label field-matching, 150k/yr), baseline stated (5-10 min/label), wedge prototype not platform |
| 2 | Augment, don't replace judgment | Screening-assistant framing; "ready for agent sign-off"; reviewer-override with audit columns (TODO) |
| 3 | Foundations first | M0 spike before UI; eval harness is the first artifact; logging/metrics in M1 |
| 4 | Governance as design input | No PII, log redaction, statutory provenance, no person-scoring anywhere — M-24-10-shaped by construction |
| 5 | Confidence routes, never approves | Word-confidence + coverage gates route to NEEDS REVIEW with reason codes; no auto-approval state exists |
| 6 | Safeguards as features | Evidence crops, preprocessing audit trail, word-level diffs, export with original/final/overwritten columns |
| 7 | Artifacts scale expertise | UI constants block, error taxonomy, runbook, API contract — templates the next contractor inherits |
| 8 | Register and publish early | docs/ tree is the register: plan, decisions, reviews, research — before code exists |
| 9 | Drift monitoring as operations | Verdict-distribution counters as OCR-regression canary; pinned engines; snapshot evals; /metrics-lite |
| 10 | Publish the numbers | Measured p50/p95 with hardware context in README; CI fails when the 5s budget breaks; benchmark artifacts (adopted) |

Read against the failure-modes trilogy: every success practice here is a failure mode inverted. The agencies that win pick one queue (vs. big-bang), keep humans deciding (vs. Robodebt), build the boring substrate (vs. pilot-to-production chasm), and publish real numbers (vs. permanent-demo purgatory) — which is, point for point, the shape this plan already has.
