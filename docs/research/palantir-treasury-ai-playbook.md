# Palantir's Offerings as a Playbook — Top 10 Strategies, Tactics, and Operations for Treasury AI Modernization

Researched 2026-07-31. Sources: Palantir's own architecture docs ([AIP + Foundry + Apollo](https://www.palantir.com/docs/foundry/architecture-center/platforms), [AIP architecture](https://www.palantir.com/docs/foundry/architecture-center/aip-architecture), [platform overview](https://www.palantir.com/docs/foundry/platform-overview/overview)), the [Federal DS Handbook's Palantir guide](https://aporb.github.io/federal-ds-handbook-site/platforms/palantir.html), the [NVIDIA Nemotron sovereign open-models launch](https://blogs.nvidia.com/blog/palantir-secure-ai-us-agencies-nemotron-open-models/) ([BusinessWire](https://www.businesswire.com/news/home/20260629390275/en/Palantir-Launches-Engine-for-Deploying-NVIDIA-Nemotron-Open-Models-in-Sovereign-Environments)), and the [forward-deployed-engineering analysis](https://getperspective.ai/blog/palantir-forward-deployed-engineering-playbook-anthropic-openai-copying). Palantir is studied here as *doctrine to learn from*, not a procurement endorsement — each item is translated into what a Treasury bureau (like TTB) should demand from any AI modernization, Palantir-built or not.

Context for scale: civil agencies (DHS, HHS, NIH, NASA, DOJ) run on Foundry; the Army's July 2025 **$10B/10-year Enterprise Service Agreement consolidated 75 contracts into one**; Maven became a Pentagon Program of Record in March 2026.

---

## Strategy

### 1. Build an Ontology: one semantic layer where data, logic, action, and security meet

The heart of the architecture: "the Ontology integrates an enterprise's data, logic, action, and security policies into an intuitive representation that **both humans and AI agents can wield**." The strategic insight is that the durable asset isn't any model or app — it's the machine-readable model of the *business*: its objects (application, label, verdict), their relationships, the actions allowed on them, and who may take them. Every AI investment then compounds against that layer instead of fragmenting into point solutions.

### 2. Sovereign AI with open weights: the model comes to the data, tuned in-house

The June 2026 Nemotron engine lets agencies run open models inside sovereign environments and **"change the weights of models themselves based on proprietary data, mission outcomes, user actions, in-platform evaluations, and post-training signals"** ([AIwire](https://www.hpcwire.com/aiwire/2026/06/29/palantir-launches-engine-for-deploying-nvidia-nemotron-open-models-in-sovereign-environments/)). The doctrine: open weights + agency infrastructure + agency feedback loops = capability the agency *owns*, with no data leaving the boundary — the national AI Action Plan's open-model argument made operational.

### 3. Sell (and buy) outcomes through consolidated vehicles, not 75 fragmented contracts

The Army ESA pattern — one framework, volume pricing, usable across components — is the procurement strategy GAO keeps asking for: consolidate, make capability available department-wide, price by consumption. For Treasury: TCSC-style shared vehicles beat bureau-by-bureau re-procurement.

### 4. Make accreditation a platform property, not a project phase

Palantir's stack is accredited FedRAMP through **DoD IL5/IL6**, and **FedStart** "lets third-party software vendors deploy their products inside Palantir's existing security accreditation envelope." Strategic translation: compliance inheritance is a product. A bureau should build (or demand) platforms where new use cases inherit the ATO instead of re-earning it — the 18-month FedRAMP paperwork Marcus described, amortized once.

## Tactics

### 5. AI acts only through governed Actions — proposal/approval built into the substrate

In the Ontology, AI doesn't write to systems directly; it invokes typed **Actions** with security policies, approvals, and full audit built in. The tactic that makes "human in the loop" real: the loop is enforced by the data layer, not by UI convention. An agent can *propose* a label rejection; only a warranted human action *executes* it.

### 6. k-LLM: model-agnostic routing so no single vendor gates the mission

AIP's "k-LLM paradigm" provides "secure connectivity to large language models" — plural, swappable, per-task ([AIP architecture](https://www.palantir.com/docs/foundry/architecture-center/aip-architecture)). Models are treated as interchangeable compute behind a governed interface; the agency's leverage and exit rights are preserved by design.

### 7. Evals as the production governor, not a launch artifact

AIP ships "a comprehensive **Evals framework for governing AI workflows in production**" — evaluation suites wired into the deployment path so a workflow that regresses doesn't ship. Same doctrine as the national plan's "evaluations ecosystem," implemented as a gate rather than a report.

### 8. Forward-deployed engineering and the bootcamp: working software on real data in under a week

The FDE model — engineers embedded with the customer, building against live mission data — plus the **AIP bootcamp**: "three-to-five-day intensive deployments," over 1,000 run by end of 2024, converting at high rates into contracts ([Perspective AI](https://getperspective.ai/blog/palantir-forward-deployed-engineering-playbook-anthropic-openai-copying)). The tactic: time-to-first-working-thing is the sales motion, the requirements process, and the risk reduction, all at once. (It's also the take-home-exercise doctrine: the evaluator's 30 minutes is a bootcamp.)

## Operations

### 9. Apollo: continuous delivery into disconnected, classified, and edge environments

Apollo autonomously ships software into environments cloud CD can't reach — air-gapped, classified, edge — keeping hundreds of sovereign deployments current from one control plane ([platforms overview](https://www.palantir.com/docs/foundry/architecture-center/platforms)). The operational answer to Marcus's firewall: don't exempt the disconnected environment from modern delivery; build delivery that treats it as a first-class target.

### 10. Lineage, purpose-based access, and audit as always-on operations

Foundry's operating posture: every dataset and derived object carries lineage; access is scoped by purpose and propagated through transformations; every action is auditable after the fact. Operationally, this is what turns "trust us" into "check us" — the property that let one platform clear DOJ, HHS, and IL6 workloads alike.

---

## Mapping to Treasury AI modernization — and to this repo

| # | Palantir doctrine | Treasury/TTB translation | This repo's instance |
|---|---|---|---|
| 1 | Ontology | Model COLA's world once: Application, Label, Field, Verdict, Agent, Action — shared by every future tool | Typed verdict/evidence schema + versioned API envelope is a micro-ontology |
| 2 | Sovereign open weights | On-prem open models tuned on TTB's own label corpus and agent feedback | Local PaddleOCR now; on-prem VLM assist behind `Extractor` (TODO) is the sovereign path |
| 3 | Consolidated vehicles | TCSC as Treasury's ESA; bureau tools packaged for reuse | Single Docker artifact, commodity stack — TCSC-compatible by design |
| 4 | Accreditation inheritance | New use cases deploy inside an existing ATO envelope | Keyless, egress-free, stateless = smallest possible accreditation surface |
| 5 | Governed Actions | AI proposes; warranted humans execute; audit built in | Screening verdicts never approve; reviewer-override writes original/final/overwritten (TODO) |
| 6 | k-LLM model agnosticism | No single model vendor gates a Treasury mission | `Extractor` interface; engine swap is a config change, proven at M0 (Paddle vs tesseract.js) |
| 7 | Evals govern production | Eval gates in the deployment path department-wide | Golden-set harness + CI latency/reachability gates block merge, not just inform |
| 8 | FDE + bootcamp | Days-to-working-demo on real data as the modernization motion | "Try a sample" 60-second evaluator path; five named proof points; deployed URL |
| 9 | Apollo-style delivery | Firewalled TTB environments get continuous delivery, not exemptions | Same image runs laptop/cloud/on-prem; models baked; no-egress CI test proves it |
| 10 | Lineage + audit always-on | Every AI-assisted verdict reconstructable after the fact | Request-ID stage logs, evidence provenance (bbox → crop), decision audit trail |

The synthesis: Palantir's genuinely transferable insight is that **the platform properties — ontology, governed actions, evals-as-gates, sovereign delivery, inherited accreditation — are the product**, and models are replaceable tenants. That is also precisely the shape PLAN.md landed on at prototype scale: a typed domain model, humans holding the only approval authority, eval gates in CI, one artifact that runs anywhere behind the firewall. A bureau that internalizes the doctrine can demand it from any vendor — including Palantir.
