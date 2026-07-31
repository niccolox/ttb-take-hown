# The COLA Pre-Screening Market — and the Case for Nationalizing or Democratizing It

Researched 2026-07-31. Companion to `cola-swot.md`. Question: who profits from checking alcohol labels *before* TTB sees them, and what would it mean to make that capability public (nationalize) or common (democratize)?

---

## 1. The market as it stands

Four tiers monetize the gap between "150k applications/year" and "47 agents reviewing by eye":

**Tier 1 — Enterprise compliance suites.** [Sovos ShipCompliant](https://sovos.com/shipcompliant/) (COLA submission integrated to TTB, tax + registration engines, "Market Ready" product) anchors the segment; beverage SaaS runs **$50-80/user/month, with small businesses at $1,500-3,000/month** all-in ([SimplyDepo](https://simplydepo.com/industry/beverage-distribution-software/), [FitGap](https://us.fitgap.com/search/compliance-software/brewery)). Label checking is bundled into a broader tax/logistics lock-in.

**Tier 2 — Point pre-screen SaaS.** [COLAClear](https://www.colaclear.com/) (public beta May 2026: reads label artwork, checks against 27 CFR Parts 4/5/16, 34 cited checks per label, "pass/review/fail in seconds"), [COLA Cloud](https://colacloud.us/), [Signify](https://www.getsignify.com/) — the direct commercialization of the take-home's exact problem.

**Tier 3 — Services.** Law firms and consultancies ([Park Street](https://www.parkstreet.com/alcoholic-beverage-services/compliance/), bevlaw, Clear Beverage Law, Malkin) selling human pre-review, rejection rescue, and resubmission management — priced per engagement, opaque, and thriving *because* rules are complex and reviewers inconsistent.

**Tier 4 — Open artifacts.** The GitHub take-home ecosystem this repo surveyed (seven working open prototypes), TTB's own published label-examples guide, and the public COLA registry — free capability nobody has assembled into a maintained commons.

**Dynamics.** The market's revenue is a tax on three public-sector gaps: rule complexity (unpriced), reviewer inconsistency (documented in `cola-swot.md`), and zero TTB-side pre-submission tooling beyond form validation. Every dollar in Tiers 2-3 is a symptom: applicants pay privately to predict what a public process will decide. And the failure modes compound at the bottom of the market — the craft brewer least able to afford $3k/month is the one most damaged by a rejection cycle or a shutdown backlog.

## 2. Pathway A — Nationalize: TTB-owned pre-screening as public infrastructure

**The move:** build the pre-screen *into* COLAs Online — instant, free, advisory field-checking at submission time (exactly this repo's architecture: OCR + deterministic cited rules + human authority preserved), plus a public API.

Precedents that worked:
- **IRS Direct File** — government building free software in a space intermediaries monetized; politically contested precisely because it worked.
- **login.gov / USWDS** — shared public capability that private products then build *on* rather than in front of.
- **NOAA weather data** — the state runs the sensing/forecast commons; private vendors differentiate on delivery and analytics.

What nationalization wins:
1. **Equity** — the 5-barrel brewery gets the same pre-screen quality as Diageo; the private toll booth (cola-swot threat #4) never hardens.
2. **Consistency** — one public rules engine with citations becomes the de facto interpretation, shrinking the reviewer-variance complaint at its source.
3. **Throughput** — validated-at-submission applications cut agent minutes per label; backlog surge (post-shutdown) becomes triage, not archaeology.
4. **Feedback loop** — TTB sees pre-screen telemetry (which rules fail most), turning label policy into a measured system.

What it costs/risks: appropriations exposure (the Direct File lesson — incumbents lobby against public alternatives); a *mandatory* pre-screen would be regulatory overreach, so it must stay advisory; and an official checker that's wrong carries authority a private one doesn't — the accuracy bar and the "screening, never approval" framing are non-negotiable.

## 3. Pathway B — Democratize: an open commons under the market

**The move:** publish the ingredients as public goods and let everyone — vendors included — build on them:
1. **Open rules engine** — the CFR field checks as a versioned, tested, citation-annotated open-source library (the "USWDS of label compliance"). This repo's deterministic rules engine is a seed of exactly this shape.
2. **Open golden corpus** — labeled evaluation set built from the public COLA registry + TTB's own examples guide, with ground truth and adversarial cases (title-case warnings, appellation traps). Today every vendor and every job candidate rebuilds this privately; a shared benchmark would discipline vendor accuracy claims overnight.
3. **Open API spec** — a standard verify-request/verdict envelope (this repo's versioned schema is one) so pre-screen results are portable across tools and submittable evidence someday.
4. **Open reference implementation** — a deployable, firewall-native screening assistant (this repo's PLAN, literally) that any state ABC agency, importer, or vendor can run.

What democratization wins: no single toll booth *and* no single point of political failure; vendors move up-stack to workflow/integration/service (where Sovos already lives comfortably); the benchmark makes "34 checks" claims verifiable; and TTB can adopt the commons without owning a procurement — the cheapest path through its own institutional physics (`gov-modernization-failure-modes.md` #7).

**The two pathways compose.** The realistic sequence is B-then-A: an open commons (rules + corpus + reference implementation) becomes the thing TTB adopts into COLAs Online, the way agencies adopted USWDS — nationalization by absorption rather than by procurement.

## 4. Opportunity map

| Opportunity | Pathway | Who moves | Effort | Blocked by |
|---|---|---|---|---|
| Advisory pre-screen inside COLAs Online | A | TTB (TMF-fundable; Treasury AI strategy names the use case) | M | Appropriations, vendor lobbying |
| Public pre-screen API | A | TTB | M | Same + rate/abuse design |
| Open CFR rules library w/ citations | B | Anyone (this repo is a seed) | S-M | Maintenance stewardship |
| Open golden benchmark corpus | B | Anyone; TTB blessing multiplies it | S | Label licensing hygiene (registry is public record) |
| Standard verdict/evidence schema | B | Community + TTB endorsement | S | Coordination only |
| State ABC reuse (26 states run parallel label regimes) | B | States adopting the reference impl. | M | Per-state rule variants |
| Vendor accuracy disclosure against the public benchmark | B | Market pressure once corpus exists | S | Corpus first |

## 5. Implications for this repo

1. The take-home artifact is, structurally, **the reference implementation for Pathway B**: open stack, deterministic cited rules, versioned verdict schema, firewall-native deploy. Licensing it permissively and documenting the rules engine as a standalone library would make that explicit.
2. The M0 corpus plan (registry images + TTB guide + adversarial generator) is a **proto-benchmark** — worth structuring so it could be published independently of the app.
3. The README's strategic paragraph gains a final beat: this isn't just one bureau's tool; it's the seed of public screening infrastructure that answers the market's documented failure (a private toll on a public process) in the direction both the Treasury AI strategy (shared capability, TCSC) and the national AI Action Plan (open models, open standards) already point.
