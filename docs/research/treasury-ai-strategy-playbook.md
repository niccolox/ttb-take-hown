# US Treasury AI Strategy — Top 10 Strategies, Tactics, and Operations

Researched 2026-07-31 from the primary source: [U.S. Department of the Treasury's AI Strategy for OMB Memorandum M-25-21](https://home.treasury.gov/system/files/136/Treasury-AI-Strategy.pdf) (September 2025; prepared by Paras Malik, Chief AI Officer; issued by Secretary Scott Bessent), plus the [Treasury AI use-case inventory](https://home.treasury.gov/data/ai_inventory), the [FSOC AI Innovation Series](https://home.treasury.gov/policy-issues/financial-markets-financial-institutions-and-fiscal-service/financial-stability-oversight-council/council-work/artificial-intelligence-innovation-series) (concluded May 2026), and [IRS AI governance policy IRM 10.24.1](https://www.irs.gov/irm/part10/irm_10-024-001r).

Why it matters to this repo: TTB is a Treasury bureau, and the strategy *names our project's category as a priority use case* — "Document Processing and Regulatory Intake: AI accelerates the classification, extraction, and review of high volume regulatory and financial documents, reducing manual workload and enabling faster policy or compliance action." A label-verification prototype is this sentence made concrete.

---

## Strategy

### 1. Innovation-oriented, governance-rooted — both, explicitly

The strategy's one-line thesis: "an innovation-oriented approach to AI adoption rooted in strong governance, security, and risk management." Not innovation *despite* governance; adoption speed is treated as a product of trustworthy rails. Every subsequent structure serves that dual mandate.

### 2. Pick mission-shaped use cases and name them

Seven named priorities: financial crime detection, economic forecasting, taxpayer assistance, procurement/spending oversight, **document processing & regulatory intake**, internal operations, and **accelerating legacy system modernization** ("AI translates legacy code to modern languages… faster upgrades from decades old systems"). The portfolio skews toward high-volume, pattern-matching work where humans are drowning — Sarah Chen's "drowning in routine stuff," department-scale.

### 3. Federated oversight: govern by impact tier, not by uniform gate

The load-bearing governance design: "high impact use cases receive direct oversight from the AI Governance Board" while "individual bureaus and departmental offices manage moderate to low use cases" against agency-wide standards with approved tools — because uniform maximum scrutiny would be a de facto ban. "This federated approach ensures that AI adoption remains agile, minimizes unnecessary barriers, and encourages responsible innovation."

### 4. Build shared capability once: TCSC, TCloud, and a common tool set

Congressionally approved Treasury Common Services Center to "accelerate access to a common set of AI tools, training and resources across the Department," plus an enterprise multi-vendor acquisition vehicle for AI-assisted code development open to all Treasury software organizations. Each bureau inheriting platforms instead of re-procuring them is the strategy's scaling mechanism.

## Tactics

### 5. Sandbox at a higher security tier than production needs

"Treasury's AI Sandbox enables experimentation in a higher security environment (**FISMA High versus Moderate**)… with built-in safeguards like continuous network monitoring" — experimentation runs *above* the compliance bar, not around it, so anything that works in the sandbox is already deployable-shaped.

### 6. Pilot broadly, but train everyone first

The secure AI chat pilot spans IT, operations, legal, procurement, and policy — with a hard prerequisite: "All employees are required to complete training to ensure compliance with Treasury's AI acceptable use policy" (and a published [AI System User Agreement](https://www.irs.gov/irm/part10/irm_10-024-001r) that bureau use must conform to). Adoption is gated on literacy, not enthusiasm.

### 7. Data marked, separated, and governed before models touch it

"Data restricted from use in an AI system are appropriately marked and remains separate from the AI systems" — coordinated across the Chief Data Officer, General Counsel, and Privacy offices, with expanded catalogs, metadata, and traceability. The data-boundary work happens *before* the AI work, inverting the usual failure order.

### 8. Fund cross-cutting work centrally, against pre-established criteria

"The AI Governance Board will manage a centralized funding mechanism… high-priority or cross-cutting use cases may be eligible for targeted support… evaluated against pre-established criteria to ensure resources are directed to projects with clear mission value and strong safeguards" — the TMF milestone-funding pattern, internalized.

## Operations

### 9. One coordination point with real visibility: the AI Transformation Office

The ATO "serves as the central coordination point… working with Treasury leadership, AI power users, and AI developers to provide visibility into ongoing projects, identify resource needs, and guide strategic planning," alongside the OCIO, Governance Board, and AI Council (which owns the use-case inventory and serves as the cross-component sharing hub). Every moderate/low use case reports through the Council — visibility without bottleneck.

### 10. Fast-track approvals, tracked costs, iterated controls

Operational learning loops close the strategy: pilots "build experience, refine internal controls, and inform broader implementation"; future "technical delivery teams and decision-making boards may be centrally established to reduce barriers, offering 'fast track' approvals to AI tooling… while also tracking AI costs and guardrails for security." Same foundational IT principles as everything else — "privacy, security, auditability, and incident response" — with AI-specific testing layered on. Workforce depth comes from tiered training (with GSA partnership) and a physical **AI Innovation Center** with "secure, pre-configured systems for experimentation… separate from operational networks."

---

## Mapping to this project

| # | Treasury practice | This repo |
|---|---|---|
| 1 | Innovation rooted in governance | Screening-assistant authority model; audit trail; no person-scoring — governance-shaped by construction |
| 2 | Named use case: document processing & regulatory intake | The TTB label-verification prototype *is* this use case; README should cite the strategy's own language |
| 3 | Federated, impact-tiered oversight | A moderate/low-tier bureau tool using approved open components — the tier designed to move fast under standards |
| 4 | Shared capability (TCSC/TCloud) | Single Docker artifact, commodity stack, `Extractor` interface — TCSC-compatible packaging |
| 5 | Sandbox above the compliance bar | Local-only inference, no-egress CI test, keyless deploy — runs *under* the firewall bar everywhere |
| 6 | Train before pilot | "Mother-proof" UI + runbook + sample walk-through = the training burden approaches zero |
| 7 | Data marked and separated first | No PII stored, log redaction, statutory-text provenance, fixture licensing notes |
| 8 | Central funding against criteria | M0 gate = pre-established kill/continue criteria; measured milestones unlock the next slice |
| 9 | Visibility without bottleneck | docs/ tree as the use-case register: plan, decisions, reviews, metrics — inventory-ready |
| 10 | Fast-track + cost tracking + iterated controls | CI latency/reachability gates as "fast track with guardrails"; /metrics-lite tracks the operating numbers |

The strategic alignment argument, in one line for the README: this prototype is Treasury's own strategy in miniature — a named priority use case (regulatory document intake), built in the federated tier (bureau-level, approved components), sandbox-safe (local, keyless, no egress), workforce-augmenting (agents decide, evidence shown), with measured milestones and published numbers.
