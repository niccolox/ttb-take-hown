# US Government Supply-Chain Policy: The 2026 Landscape

Research date: 2026-08-02. Anchor document: Executive Order 14415, "Securing
America's Defense Supply Chains and Ensuring Domestic Acquisition of Critical
Materials" (July 20, 2026). Scope: the anchor EO in detail; the federal
supply-chain risk management (SCRM) canon ranked top-10 and organized by
policy / strategy / operations / tactics; the Treasury-specific document
layer; and a synthesis of the 2025-2026 program. Compiled from a direct read
of the EO plus three parallel research passes. Companion doc:
`ai-supply-chain-risk.md` (AI/OCR-specific supply chain for this project).

---

## TL;DR

1. **EO 14415 is the enforcement capstone of a five-legged China-de-risking
   industrial program**: it closes the DoD waiver escape valve on covered
   materials (Jan 1, 2027), mandates supply-chain mapping to raw-material
   origin via indentured Bills of Materials, and forces domestic-source
   qualification with contract-termination teeth.
2. **The 2025-2026 period reshaped the SCRM canon**: the software-attestation
   regime was dismantled (OMB M-26-05 rescinded M-22-18/M-23-16), the
   first-ever FASCSA exclusion order issued (Acronis), CMMC went live in
   contracts, CISA's ICT SCRM Task Force was terminated, FAR Part 40 is
   consolidating everything, and new SBOM Minimum Elements published July 29,
   2026. **Center of gravity moved from software-assurance mandates to
   country-of-origin exclusion and hardware/minerals provenance.**
3. **Treasury has no public standalone SCRM policy** — its internal C-SCRM
   lives inside TD P 85-01 and FAR-inherited clauses. Its binding
   supply-chain instruments are all investment-security: outbound investment
   (31 CFR 850), CFIUS rules, and the COINS Act. Its financial-sector
   supply-chain program is advisory (cloud report, CESG, third-party
   guidance). The BeyondTrust post-incident report was never published.
4. **The design signature repeats everywhere**: statutory bans + shrinking
   waivers, origin-tracing documentation pushed onto industry, government
   equity/offtake underwriting domestic alternatives, allied carve-outs as
   the pressure valve. The same pattern is coming for AI (No Adversarial AI
   Act's FASC-list mechanism) — directly relevant to this project's
   PaddleOCR question.

---

## Part 1 — The anchor: EO 14415 (July 20, 2026)

Operationalizes **10 U.S.C. § 4872** (acquisition of sensitive materials
from non-allied foreign nations). Covered materials: samarium-cobalt and
neodymium-iron-boron magnets, tungsten metal powder and heavy alloy,
tantalum metals/alloys — with **gallium, germanium, molybdenum added by the
FY26 NDAA** (Ga/Ge effective Dec 18, 2027). Covered nations: China, Russia,
Iran, North Korea
([10 USC 4872](https://uscode.house.gov/view.xhtml?req=%28title%3A10+section%3A4872+edition%3Aprelim%29),
[Pillsbury](https://www.pillsburylaw.com/en/news-and-insights/fy2026-ndaa-sourcing-restrictions-critical-minerals-advanced-batteries.html)).

**Operative sections:**

- **§2 Waivers**: from **January 1, 2027** the Secretary of War ceases
  issuing nonavailability waivers under §4872(c)(1) except through formal
  mitigation plans demonstrating "exhaustive efforts" to source compliant
  materials; 180 days to enumerate contractual remedies. Wiley's analysis:
  waivers were previously granted "relatively freely" — this is the change
  ([Wiley](https://www.wiley.law/alert-New-Executive-Order-Expands-Supply-Chain-Due-Diligence-for-Defense-Contractors)).
- **§3 Mapping** (180 days): rulemaking requiring all primes and subs to map
  critical supply chains "from raw materials to end use products" via
  **indentured Bills of Materials**, vet suppliers for financial risk and
  foreign ownership/control/influence (FOCI), notify DoD of significant
  risks within 15 days, corrective-action plans within 45.
- **§4 Domestic source qualification** (180 days): identify
  national-security acquisitions relying on "unreliable foreign suppliers";
  contractors must qualify domestic alternates or face suspension/
  termination; 90-day acceleration strategy for testing/qualification.
- **§5**: semiannual reports to the APNSA through Jan 1, 2028. **§6**:
  exempts US-funded critical-minerals projects, naming **Project Vault**.
- **Definitions**: "unreliable foreign supplier" = FOCI of a covered nation
  per §4872(f)(2) *"or a nation otherwise designated by the Secretary"* —
  an expandable list.

**Implementation timeline** (Holland & Knight): Oct 18, 2026
qualification-acceleration strategy → Jan 1, 2027 waiver cutoff → Jan 16,
2027 mapping guidance/rulemaking → ~Apr 2027 implementing regs → Dec 18,
2027 Ga/Ge join covered materials
([H&K](https://www.hklaw.com/en/insights/publications/2026/07/president-trump-signs-executive-order-on-defense-supply-chains)).

**Industry reaction** (composite of law-firm alerts): indentured BOMs to
raw-material origin exceed most primes' current visibility;
small/lower-tier suppliers bear disproportionate burden; **False Claims Act
exposure** for misleading mitigation-plan content; open questions on what
counts as a "national security" acquisition and whether "alternative
sources" means domestic-only or allied
([EO text](https://www.whitehouse.gov/presidential-actions/2026/07/securing-americas-defense-supply-chains-and-ensuring-domestic-acquisition-of-critical-materials/),
[Fact sheet](https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-americas-defense-supply-chains-and-ensures-domestic-acquisition-of-critical-materials/),
[NLR](https://natlawreview.com/article/more-critical-minerals-order-what-defense-contractors-should-know-about-new-supply)).

---

## Part 2 — The federal SCRM canon: ranked top-10 (mid-2026)

Levels: **P**olicy (what must be true), **S**trategy (direction),
**O**perations (programs/processes), **T**actics (controls/checklists).

| # | Document | Level | Status mid-2026 | Why it's load-bearing |
|---|---|---|---|---|
| 1 | **NIST SP 800-161r1-upd1** — C-SCRM Practices (Nov 2024 update; no Rev 2 exists) | T/O | Current | The single canonical C-SCRM reference; SR control-family overlay on 800-53r5; mandatory-in-effect via FISMA/OMB A-130 ([PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-161r1.pdf)) |
| 2 | **FASCSA / 41 CFR 201 / FAR 4.23** + FY26 NDAA FASC reforms | P/O | Active, newly proven | **First-ever exclusion order issued (Acronis, eff. July 2025)**; FY26 NDAA moved FASC into EOP and broadened remit; the government-wide exclusion machine ([Crowell](https://www.crowell.com/en/insights/client-alerts/off-the-supply-chain-director-of-national-intelligence-issues-first-exclusion-and-removal-order-under-the-federal-acquisition-supply-chain-security-act)) |
| 3 | **EO 13873 + 15 CFR 791 (ICTS)** | P/O | Active, expanding | The only authority reaching *commercial* supply chains: connected-vehicles rule final (software bite MY2027), TP-Link router ban proposed, drones rerouted to FCC ([CV rule](https://www.federalregister.gov/documents/2025/01/16/2025-00592/securing-the-information-and-communications-technology-and-services-supply-chain-connected-vehicles)) |
| 4 | **NDAA §889 / FAR 52.204-25** | P | Active, relocating to FAR 40 | Still the most commonly encountered SCRM obligation; FCC Covered List expanded Dec 2025 to DJI/Autel UAS |
| 5 | **CMMC (32 CFR 170 + DFARS 252.204-7021/-7025) + DFARS 7012** | O/T | **Live in contracts since Nov 10, 2025** | 4-year phase-in to near-universal DoD coverage by Nov 2028; annual SPRS affirmations ([Cooley](https://www.cooley.com/news/insight/2025/2025-09-25-dod-releases-long-awaited-final-rule-implementing-cybersecurity-maturity-model-certification-contract-clause)) |
| 6 | **FAR Part 40** (FAR Case 2026-001) | O | Proposed June 23, 2026; final expected end-2026 | The consolidation point: absorbs §889, FASCSA, TikTok, drone rules + companion CUI rule ([IGC](https://www.insidegovernmentcontracts.com/2026/07/proposed-far-part-40-rule-consolidation-of-supply-chain-security-and-information-security-requirements-and-new-changes-to-the-rules/)) |
| 7 | **OMB M-26-05 + EO 14306** | P | Jan 2026 / June 2025 | Defines the post-attestation regime: M-22-18/M-23-16 rescinded, agency-led risk-based review replaces blanket SSDF attestation ([M-26-05](https://www.whitehouse.gov/wp-content/uploads/2026/01/M-26-05-Adopting-a-Risk-based-Approach-to-Software-and-Hardware-Security.pdf)) |
| 8 | **2026 SBOM Minimum Elements** (CISA/NSA/FBI + partners) | T | **Published July 29, 2026** | Replaces NTIA 2021 baseline; adds component hash, license, generation context ([CISA](https://www.cisa.gov/resources-tools/resources/2026-minimum-elements-software-bill-materials-sbom)) |
| 9 | **EO 14415 + NDIS 2024 + DoDI 5200.44** | S/P | EO in pre-regulatory phase | The defense-industrial SCRM direction: hard Jan 2027 waiver cutoff, supply-chain-mapping rulemaking, atop the first National Defense Industrial Strategy |
| 10 | **NDAA FY23 §5949** (semiconductors) + Feb 2026 proposed FAR rule | P | Final rule expected pre-deadline | The **Dec 23, 2027 cliff**: no SMIC/YMTC/CXMT chips in procured electronics; chip-level provenance work must start now ([FR](https://www.federalregister.gov/documents/2026/02/17/2026-03065/federal-acquisition-regulation-prohibition-on-certain-semiconductor-products-and-services)) |

**Bubbling under**: EO 14017 corpus + Quadrennial Supply Chain Review (Dec
2024) — deepest analytic baseline, politically dormant (EO 14239 listed it
for "review and modification"; no Council activity under this
administration); Trump Cyber Strategy for America (Mar 2026, supersedes the
2023 National Cybersecurity Strategy in practice); National
Counterintelligence Strategy 2024 (Pillar 2 = supply chains); NIST SP
800-218 SSDF v1.2 draft (Dec 2025, final expected late 2026); EO 14241
critical minerals; GAO's seven-practices ICT SCRM audit yardstick
(GAO-21-171 line).

**Structural shifts a practitioner must internalize:**
1. Software-assurance *mandates* (2021-2024) → country-of-origin *exclusion*
   and hardware/minerals *provenance* (2025-2026).
2. Compliance text consolidating into FAR Part 40 and DFARS; OMB memos now
   delegate rather than mandate.
3. The public-private collaborative layer is gone — CISA's ICT SCRM Task
   Force terminated (post-EO 14217/CIPAC termination, early 2025); its
   products (Vendor SCRM Template, HBOM framework) survive as frozen
   references. Secure by Design continues only as a voluntary pledge.

---

## Part 3 — The Treasury layer

### 3.1 Treasury's own house (internal + acquisition)

- **TD 85-01 / TD P 85-01** (IT Security Program): the binding internal
  directive through which NIST 800-53 controls — including the SR
  supply-chain family — bind Treasury bureaus. **There is no separately
  published, public, standalone Treasury SCRM policy**; the current TD P
  85-01 handbook is not publicly posted
  ([TD 85-01](https://home.treasury.gov/about/general-information/orders-and-directives/td85-01)).
- **DTAR (48 CFR Ch. 10) + DTAP**: no Treasury-unique supply-chain subpart —
  Treasury's acquisition-side SCRM is entirely FAR-inherited (Kaspersky
  52.204-23, §889 52.204-24/-25/-26, FASCSA 52.204-28/-29/-30, soon FAR 40).
- **BeyondTrust incident (Dec 2024)**: the foundational primary document is
  Treasury's Dec 30, 2024 FISMA major-incident letter to Senate Banking
  (APT27/Silk Typhoon; stolen SaaS API key + CVE-2024-12356/-12686; OFAC,
  OFR, CFIUS-office workstations). **The 30-day supplemental report was
  delivered to Congress late Jan 2025 but never published; no dedicated
  GAO or Treasury-OIG report on the incident exists as of Aug 2026** —
  accountability artifacts are the Senate letters, DOJ's Mar 2025
  indictment, and two adjacent GAO reports
  ([letter](https://www.banking.senate.gov/imo/media/doc/lettertosecretaryyellenonccpcyberbreach.pdf)).
- **GAO-26-107668** (May 2026): Treasury's §889 posture — no covered PRC
  telecom equipment on networks per 2019-2025 searches; one facility had
  non-networked covered analog cameras, being replaced
  ([GAO](https://www.gao.gov/products/gao-26-107668)).

### 3.2 Treasury as financial-sector regulator (advisory-heavy)

- **Treasury Cloud Report** (Feb 2023): six challenges incl. CSP
  transparency gaps, concentration risk, weak negotiating leverage — the
  systemic cloud-supply-chain assessment
  ([CESG page](https://home.treasury.gov/about/offices/domestic-finance/financial-institutions/cloud-executive-steering-group)).
- **Cloud Executive Steering Group deliverables** (June-July 2024): Cloud
  Profile 2.0, Cloud Outsourcing Issues & Considerations, secure-by-design
  transparency doc, Cloud Lexicon, coordinated-examination initiative.
- **Interagency Third-Party Risk Guidance** (OCC/Fed/FDIC, June 2023): the
  operative examination standard for bank vendor/supply-chain risk —
  lifecycle framework (planning → due diligence → contract → monitoring →
  termination), fourth-party exposure
  ([FR](https://www.federalregister.gov/documents/2023/06/09/2023-12340/interagency-guidance-on-third-party-relationships-risk-management)).
- **FSOC Annual Reports 2024/2025**: third-party service providers as a
  named vulnerability; standing (unfulfilled) ask that Congress grant
  direct service-provider examination authority; the 2025 report (first
  under this administration, otherwise deregulatory) still elevates
  cybersecurity/third-party risk and endorses coordinated TSP examinations.
- **Treasury AI reports** (Mar 2024 cyber-risk report; Dec 2024 RFI
  synthesis): both frame AI as a **supply-chain amplifier** — extended
  vendor/data/infrastructure chains, model and data provenance opacity,
  provider concentration
  ([AI report](https://home.treasury.gov/system/files/136/Artificial-Intelligence-in-Financial-Services.pdf)).
- **FSSCC**: SIFMA-FSSCC Reconnection Framework 2025 (criteria for
  reconnecting to a counterparty after a destructive cyber event).

### 3.3 Treasury as national-security actor (the binding instruments)

- **Outbound Investment Security Program** (31 CFR 850, effective Jan 2,
  2025): prohibits/notifies US investment into PRC semiconductors, quantum,
  AI ([rule](https://www.federalregister.gov/documents/2024/11/15/2024-25422/provisions-pertaining-to-us-investments-in-certain-national-security-technologies-and-products-in)).
- **COINS Act** (in FY26 NDAA, signed Dec 18, 2025): codifies and expands
  the program — adds hypersonics and HPC categories, extends beyond China;
  new Treasury regs due by Mar 13, 2027
  ([Baker McKenzie](https://sanctionsnews.bakermckenzie.com/president-trump-signs-coins-act-codifying-and-expanding-outbound-investment-regulations/)).
- **CFIUS hardening** (Nov 2024 rules): real-estate jurisdiction expanded to
  227 listed installations; penalties raised $250k → $5M per violation.
- **CFIUS fast-track / Known Investor Program** (announced May 2025; RFI
  Feb 2026): allied-investor fast lane conditioned on "verifiable distance"
  from adversary countries — America First Investment Policy implementation.
- **OFAC as supply-chain enforcement**: the 2019 Compliance Framework
  (risk assessment extends to supply chains and intermediaries) + tri-seal
  notes on third-party evasion; 2025 settlements holding importers liable
  for component-origin exposure.

**Net Treasury picture**: internal SCRM is inherited (NIST + FAR), the
financial-sector program is advisory, and **the true binding center of
gravity is investment security — all of it technology-supply-chain
focused** (semis, quantum, AI, hypersonics).

---

## Part 4 — How the 2025-2026 program fits together

The administration dismantled the Biden-era coordination architecture (EO
14017 reviews and the Supply Chain Resilience Council are dormant; no
standing council replaced them — coordination runs ad hoc through
NSC/APNSA, the National Energy Dominance Council, Commerce, and
DoD/"Department of War") and rebuilt supply-chain policy as five
interlocking legs:

1. **Demand-side compulsion (defense procurement)** — EO 14415 + FY26 NDAA
   §§837/848/1412: sourcing bans with the waiver valve closing, indentured
   BOM mapping, FOCI vetting, $2B National Defense Stockpile
   recapitalization.
2. **Supply-side buildout (minerals)** — EO 14241 (DPA Title III,
   permitting fast-track); the **MP Materials template** (July 2025: DoD
   takes ~15% equity, $110/kg NdPr price floor, 10-year magnet offtake);
   **Project Vault** (Feb 2026: $12B public-private civilian minerals
   reserve, $10B EXIM + private capital — explicitly exempted by EO 14415
   §6). Stick and carrot are deliberately paired.
3. **Trade wall (Section 232)** — chips 25% with fab-investment carve-outs
   (Jan 2026), copper 50%, pharma 100%-paused, critical minerals held for
   negotiation rather than tariffed (Jan 2026) — tariffs price allies in,
   not just adversaries out.
4. **Capital screening (Treasury's leg)** — CFIUS fast-track for allies /
   block-not-mitigate for China; outbound restrictions expanding via COINS;
   subsidy programs converted to equity stakes (Intel ~10% via CHIPS
   conversion, Aug 2025).
5. **Tech/data complement (ICTS + FASC)** — class-based rules excising
   adversary hardware/software from commercial networks (vehicles final;
   TP-Link proposed; drones rerouted to FCC), with the congressional track
   (FASC Improvement Act — passed House committee Feb 2026; **No
   Adversarial AI Act** — would have FASC list foreign-adversary AI within
   60 days) extending list-based exclusion to AI and ICT vendors.

**Common design signature**: statutory bans + shrinking waivers,
origin-tracing documentation duties pushed onto industry, government
equity/offtake underwriting domestic alternatives, allied carve-outs as the
pressure-release valve. Adjacent applications of the same pattern: pharma
(EO 14293 + the SAPIR six-month API reserve, Aug 2025) and maritime (EO
14269 + the Feb 2026 Maritime Action Plan).

---

## Part 5 — Relevance to this project (Label Check / TTB)

The pattern documented above is exactly the trajectory
`ai-supply-chain-risk.md` flags for our PaddleOCR stack:

1. **List-based exclusion is coming to AI.** The FASCSA machine is proven
   (Acronis), the FASC's remit was just broadened, and the No Adversarial
   AI Act would point that machine at foreign-adversary AI. A
   Baidu-produced ML stack in a Treasury-facing tool sits squarely in the
   blast radius of the mechanism Congress is building — the migration path
   in the companion doc is the hedge.
2. **Origin-tracing is the new compliance currency.** EO 14415's indentured
   BOMs for metals are the hardware analogue of SBOMs for software. Our
   planned SBOM (TODOS) should follow the **2026 SBOM Minimum Elements**
   (July 29, 2026 — component hash, license, generation context), which
   maps directly onto our weight-checksum and hash-locked-requirements
   items.
3. **M-26-05 defines the review we'd actually face**: no blanket
   attestation, but an agency-led risk assessment — where a clean SBOM,
   pinned hashes, air-gapped runtime, and a documented migration path are
   the strongest available answers.
4. **Treasury's institutional posture**: post-BeyondTrust, Treasury's
   supply-chain sensitivity is a PRC-actor-via-third-party-software story.
   Its own AI reports frame AI as a supply-chain amplifier. Both cut
   against PRC-origin components and for the US-domestic preference the
   companion doc recommends.

## Caveats

- 2026-dated items rest partly on law-firm alerts and trade press
  (marked inline); re-verify against the Federal Register / primary pages
  before formal citation. eCFR.gov blocks automated fetches — use the
  Cornell LII mirror for CFR text.
- Moving targets to track: FAR Part 40 finalization (end-2026), EO 14415
  DFARS rulemaking (through 2027), §5949 final rule, No Adversarial AI Act
  / FASC Improvement Act, COINS implementing regs (due Mar 2027), the
  TP-Link ICTS decision.
- Negative findings worth remembering: no public Treasury SCRM policy, no
  published BeyondTrust post-incident report, no dedicated
  GAO/OIG BeyondTrust audit, no active EO 14017 machinery.
