# Top 10 Success Strategies, Tactics, and Operations for Government Modernization

Researched 2026-07-31. The inverse of `gov-modernization-failure-modes.md`: what the modernizations that *work* actually do, drawn from the GAO Agile Assessment Guide, the Technology Modernization Fund's operating model, GDS/USDS practice, and published federal delivery numbers. Grouped as **strategy** (what to decide), **tactics** (what to build), **operations** (what to run), with a closing map to this repo's PLAN.md.

The headline numbers: TMF-funded projects show an **80% success rate against the 13% baseline** for large government projects ([TMF/Wikipedia](https://en.wikipedia.org/wiki/Technology_Modernization_Fund)); GSA reports agile delivery cutting costs ~25% versus waterfall with 40-60% faster time-to-market, and holding overruns to 10-15% where traditional projects blow budgets by 100-200% ([Agile36](https://www.agile36.com/blog/agile-in-government-2026)).

---

## Strategy

### 1. Strangle the monolith; never big-bang it

GDS transformed services "by breaking down monolithic systems into smaller, manageable components and delivering value incrementally rather than attempting a massive overhaul"; the strangler-fig pattern replaces old functionality gradually while the legacy system keeps running ([FasterCapital](https://fastercapital.com/content/Government-Agile-Methodologies-Agile-Governance--Navigating-Bureaucracy-for-Startup-Success.html)). The $4.2M-rebuild-quote path fails; the wedge that coexists with the incumbent ships.

### 2. Fund milestones, not promises

The TMF model: "agencies unlock funding transfers only as they complete project milestones," with board-level technical coaching attached to the money ([tmf.cio.gov](https://tmf.cio.gov/about/), [GSA](https://www.gsa.gov/technology/government-it-initiatives/technology-modernization-fund)). Incremental funding is the financial twin of incremental delivery — it converts sunk-cost momentum into kill-or-continue decisions at every gate, which is precisely why the 80%-vs-13% gap exists.

### 3. Deliver value in the first quarter, not the fifth year

GAO's Agile Assessment Guide exists because "software developed incrementally and continuously evaluated for functionality, quality, and customer satisfaction… can reduce the risks of funding a program that fails or produces outdated technology" ([GAO-24-105506](https://www.gao.gov/products/gao-24-105506), [guide PDF](https://www.gao.gov/assets/720/710147.pdf)). The first working slice in users' hands is both the risk reducer and the political capital that funds slice two.

### 4. Prioritize by mission value, replace by component

FAS's scaling analysis and the TMF investment criteria converge: pick "high-value components for incremental replacement" — modular architecture, automated processes, shared services — not whole-system rewrites ([FAS](https://fas.org/publication/scaling-proven-it-modernization-strategies-across-the-federal-government/), [TMF investments](https://tmf.cio.gov/investments/)). The component boundary is the risk boundary.

## Tactics

### 5. Put a real product owner on it, with documented authority

GAO's most repeated agile finding: define and document "the roles and responsibilities among product owners, the solution team, and other relevant stakeholders for prioritizing and approving" work ([GAO-24-105506](https://www.gao.gov/products/gao-24-105506)). Modernizations fail integration when nobody owns the product; a named owner with priority authority is the cheapest structural fix in the playbook.

### 6. Build with the users, in their language, from week one

The GDS/USDS canon — user research before build, plain language, "show the thing" at every demo — is what separated voter-registration-class successes from NPfIT-class failures; services designed with clinicians/agents/citizens get adopted, services designed for them get worked around. (The failure-mode doc's #5 and #6, inverted.)

### 7. Make the safe path the easy path: platforms and shared services

TMF explicitly favors "utilization of existing shared services"; USDS institutionalized experimentation with its 10x program (10% time to explore without repercussions) ([FasterCapital](https://fastercapital.com/content/Government-Agile-Methodologies-Agile-Governance--Navigating-Bureaucracy-for-Startup-Success.html), [TMF](https://tmf.cio.gov/)). Login.gov-style platforms mean each modernization inherits identity, hosting, and compliance instead of re-solving them — the compounding tactic.

## Operations

### 8. Continuous evaluation against user satisfaction, not milestones alone

GAO's agile monitoring practices center on continuous evaluation "for functionality, quality, and customer satisfaction" — meaning working software demos and user metrics as the program-control instrument, not earned-value paperwork ([GAO guide PDF](https://www.gao.gov/assets/720/710147.pdf)). Green status reports with decaying usage is the failure signature; usage *is* the status report.

### 9. Keep the legacy system running and the rollback real

The strangler pattern's operational half: "maintaining service continuity" while components migrate ([FasterCapital](https://fastercapital.com/content/Government-Agile-Methodologies-Agile-Governance--Navigating-Bureaucracy-for-Startup-Success.html)). Cutover is a reversible operation with a rehearsed rollback, or it's a bet-the-agency event. Healthcare.gov's rescue began the day rollback and iteration became possible.

### 10. Publish delivery metrics and reuse what they teach

GSA's published agile-vs-waterfall numbers (25% cost, 40-60% speed, 10-15% overrun banding) are themselves an operational practice: measured delivery data, published, becomes the argument for the next project and the calibration for estimates ([Agile36](https://www.agile36.com/blog/agile-in-government-2026), [GSA IT modernization blog](https://gsablogs.gsa.gov/technology/tag/it-modernization/)). Agencies that don't measure delivery re-litigate methodology forever; agencies that do, compound.

---

## Mapping to this project

| # | Success practice | PLAN.md implementation |
|---|---|---|
| 1 | Strangler, not big-bang | Standalone wedge beside COLA; no integration bet; informs procurement instead of replacing the system |
| 2 | Milestone-gated funding | M0 feasibility gate before UI money; kill-or-pivot criteria written down (engine fallback ladder) |
| 3 | Value in the first slice | M1 ships a deployed, demoable verify loop with failure states — the first slice is usable, not scaffolding |
| 4 | Component-boundary risk | Extractor interface, pure rules engine, locator as named component — each replaceable alone |
| 5 | Product ownership | Single-owner take-home now; decision audit trail (34 logged calls) is the ownership record a successor inherits |
| 6 | Build with users, in their language | UI copy specified verbatim in plain language; Jenny's checklist order; Dave's override (TODO); evaluator-as-user M1 items |
| 7 | Shared/boring platforms | Commodity stack (FastAPI, PaddleOCR, Docker); no bespoke infra; USWDS-derived visual language |
| 8 | Continuous evaluation | Golden-set evals + verdict-distribution monitoring + CI latency/reachability assertions run every build |
| 9 | Continuity and rollback | Agents' manual process untouched (screening assistant); stateless single-image deploys = rollback in minutes |
| 10 | Publish delivery metrics | Measured p50/p95 with hardware context in README; benchmark artifacts committed (adopted from competitor survey) |

Read with the other four research docs, the pattern closes: the failure literature says government projects die on adoption physics, delivery structure, and institutional physics; the success literature says the survivors invert exactly those — one component at a time, funded by demonstrated milestones, built with the users, measured in public. The five docs together are the argument that this plan's shape — wedge-sized, M0-gated, human-deciding, metric-publishing — is not style but survivorship.
