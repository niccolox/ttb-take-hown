# COLA (Certificate of Label Approval) — Multi-Voice SWOT

Researched 2026-07-31. COLA is the TTB approval every alcohol label needs before market (27 CFR; FAA Act). The system of record is **COLAs Online** (launched 2003): **2.9M+ electronic COLAs issued, ~2,500 new approvals/week**; current median processing **wine 4 days, spirits 6 days, malt 1 day** (half take longer; historically 5-20 days), with human review retained behind built-in application validations ([TTB processing times](https://www.ttb.gov/regulated-commodities/labeling/processing-times), [COLAs Online FAQs](https://www.ttb.gov/faqs/colas-and-formulas-online-faqs/print), [COLA Cloud guide](https://colacloud.us/blog/what-is-a-cola)).

SWOT below is synthesized from five voices: **vendors** (software + law/compliance services), **users** (applicants and the agents who review), **industry** (trade associations), **media**, and **internet gossip** (compliance blogs and forum-adjacent chatter).

---

## Strengths

- **It works at volume, free, online** *(user)*: 24/7 electronic filing, status checking, correction-instead-of-rejection workflows; median turnarounds of 1-6 days in 2026 are genuinely fast for a federal approval ([TTB](https://www.ttb.gov/regulated-commodities/labeling/processing-times)).
- **Built-in validations reduced error churn** *(user/vendor)*: the online application "prevents many errors made on paper applications" and lets applicants correct rather than resubmit ([TTB FAQs](https://www.ttb.gov/faqs/colas-and-formulas-online-faqs/print)).
- **The public registry is an asset** *(industry/vendor)*: a searchable database of millions of approved labels is de facto open data — competitors, lawyers, and (as our competitor survey showed) test-fixture builders all mine it.
- **Allowable-changes flexibility** *(industry)*: TTB's list of label changes permitted *without* a new COLA is real regulatory pragmatism, publicized by trade groups during shutdowns ([Wine Institute](https://wineinstitute.org/news-alerts/government-shutdown-ttb-guidance-on-allowable-cola-changes/)).
- **Two decades of institutional continuity** *(media framing inverted)*: "obscure" also means stable — the process is well-understood by every player in the market.

## Weaknesses

- **Single point of failure with zero surge capacity** *(user/media)*: the October 2025 shutdown sent **85%+ of TTB staff home**; no COLAs, formulas, or permits processed at all; reopening brought weeks of backlog ([Inc.](https://www.inc.com/jennifer-conrad/shutdown-fallout-ttb-government-office-hurting-spirits-industry-holidays/91269738), [Brewbound](https://www.brewbound.com/news/with-government-reopened-ttb-begins-processing-backlog-of-beer-labels/), [Brewers Association](https://www.brewersassociation.org/government-affairs-updates/ttb-shares-timeline-and-tips-for-faster-approvals-after-shutdown/)).
- **Human review is the throughput ceiling** *(user)*: the take-home brief's own numbers — 47 agents, 150k applications/year, 5-10 minutes of eyeballing each — describe the bottleneck; TTB's FAQ confirms "the process of human review… remains."
- **Inconsistency between reviewers** *(gossip)*: compliance blogs document approvals "terribly inconsistent with the prescribed federal regulations," reviewers who needed to be "schooled… on a commonly used label item" (AVA appellations), and profane labels approved while tamer ones bounce ([Wine Compliance Alliance](https://winecompliancealliance.com/what-the-ttb-gets-wrong-in-label-approvals/), [AHSO Insights](https://www.ahsoinsights.com/p/what-the-ttb-wont-tell-you)).
- **Rule complexity produces rejection churn** *(vendor)*: "with so many technical rules, many labels are initially rejected or held up" — the error classes are stable and well-known (warning formatting, appellations, class/type) ([Blue Label](https://www.bluelabelpackaging.com/blog/3-reasons-why-the-ttb-turned-down-your-cola-and-how-to-avoid-them/), [Malkin Law](https://www.malkinlawfirm.com/blog/2026/03/ttb-labeling-requirements-what-alcohol-brands-keep-getting-wrong/)).
- **Loopholes in the exemption path** *(gossip/industry)*: certificate-of-exemption filings let labels carry appellations (e.g., "Napa Valley") the blend didn't earn — a documented gap regulators are patching ([Wine Compliance Alliance](https://winecompliancealliance.com/ttb-updates-label-approval-exemptions-bulk-wine-market/)).

## Opportunities

- **A pre-screen software market already exists** *(vendor)*: COLAClear (34 CFR-cited checks per label, public beta 2026), COLA Cloud, Signify, plus law firms (bevlaw, Clear Beverage Law) productizing the complexity — evidence that automated first-pass checking is commercially validated, and that TTB itself is the under-tooled party.
- **AI-assisted agent triage** *(user/industry)*: the exact wedge this repo plans — routine field-matching automated, agent judgment preserved — attacks the throughput ceiling without touching approval authority; Treasury's own AI strategy names "document processing and regulatory intake" as a priority use case.
- **Backlog surge resilience** *(industry)*: a screening assistant is precisely what turns a post-shutdown backlog from weeks into days; ACSA/BA advocacy shows the demand is organized and vocal ([ACSA](https://americancraftspirits.org/acsa-welcomes-end-of-government-shutdown-and-return-of-ttb-services/)).
- **Consistency as a product** *(gossip inverted)*: deterministic, citation-backed checks answer the loudest community complaint — inconsistent reviewers — with per-field regulatory sources (the COLAClear pattern, adopted in our TODOS).
- **Open registry as training/eval corpus** *(vendor)*: real approved/rejected labels with agency reasoning (TTB's own published label-examples guide) are free, authoritative ground truth — already adopted into this repo's M0 corpus plan.

## Threats

- **Political fragility outranks technical fixes** *(media)*: no software survives a lapsed appropriation; Q4 concentration (30-40% of annual craft-spirits sales) makes shutdown timing existential for small producers — and makes TTB a recurring bad-news story it doesn't control ([Inc.](https://www.inc.com/jennifer-conrad/shutdown-fallout-ttb-government-office-hurting-spirits-industry-holidays/91269738)).
- **Automation-trust backlash** *(user/gossip)*: agents already distrust modernization (the brief's Dave; the 2008 phone system); a false-PASS incident on a statutory warning would be a legitimacy failure, not a bug (see `gov-ai-failure-modes.md`).
- **Deregulatory pressure on the mandate itself** *(industry)*: exemption expansion and label-approval streamlining proposals could shrink the review function the tooling serves; conversely, labeling-rule additions (allergens, nutrition) could balloon complexity faster than tooling absorbs it.
- **Vendor lock-in risk in the pre-screen layer** *(vendor)*: if third-party pre-screens become de facto gatekeepers, the public process gains a private toll booth — an argument for TTB owning its own screening capability (which is what the take-home prototypes).
- **Staffing trajectory** *(user)*: 100+ agents in the 1980s → 47 now against 150k applications; attrition without tooling is the quiet threat the whole modernization case rests on.

---

## Implications for this repo

1. The SWOT's center of gravity **validates the product thesis**: the bottleneck is human-review throughput and consistency, both directly addressed by a screening assistant that never holds approval authority.
2. **Consistency is the underserved sell** — per-field regulatory citations and deterministic checks answer the community's loudest documented complaint; keep the citations TODO at P2.
3. **Backlog surge is the killer demo scenario** — the batch mode's story should be "post-shutdown Monday: 300 queued labels triaged before lunch," which is more visceral than Janet's importer.
4. The **exemption loophole and reviewer-error anecdotes** justify the tool double-checking *approved* patterns too (appellation percentage rules are a natural CFR-engine addition in TODOS).
5. The **registry-as-corpus** and **TTB-guide ground truth** adoptions already in TODOS are confirmed as the right calls — the domain's own data exhaust is the eval asset.
