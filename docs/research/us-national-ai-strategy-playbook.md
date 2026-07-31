# US National AI Strategy (Trump Administration) — Top 10 Strategies, Tactics, and Operations

Researched 2026-07-31 from the primary source: [*Winning the Race: America's AI Action Plan*](https://www.whitehouse.gov/wp-content/uploads/2025/07/Americas-AI-Action-Plan.pdf) (July 23, 2025, 28 pp; signed by Michael Kratsios/OSTP, David Sacks/AI & Crypto, Marco Rubio/NSA), issued under [EO 14179 "Removing Barriers to American Leadership in Artificial Intelligence"](https://www.whitehouse.gov/fact-sheets/2025/12/fact-sheet-president-donald-j-trump-ensures-a-national-policy-framework-for-artificial-intelligence/) (Jan 23, 2025), with the accompanying executive orders (American AI Technology Stack exports; data-center permitting; "Unbiased AI Principles" in federal procurement) via [Sidley](https://www.sidley.com/en/insights/newsupdates/2025/07/the-trump-administrations-2025-ai-action-plan) and [Latham & Watkins](https://www.lw.com/en/insights/president-trump-ai-action-plan-key-insights) analyses.

Framing, verbatim: "The United States is in a race to achieve global dominance in artificial intelligence… Whoever has the largest AI ecosystem will set global AI standards." Three pillars: **I. Accelerate AI Innovation · II. Build American AI Infrastructure · III. Lead in International AI Diplomacy and Security.** Three cross-cutting principles: workers first ("complementing their work — not replacing it"), AI "free from ideological bias… designed to pursue objective truth," and preventing theft/misuse of advanced AI.

---

## Strategy

### 1. Deregulate first: remove the barriers before building the programs

Pillar I opens with "Remove Red Tape and Onerous Regulation" — rescinding EO 14110, an OSTP RFI to find rules that hinder AI, OMB-led revision of agency regulations, and conditioning federal AI funding on states' regulatory climates. The theory: adoption speed is the bottleneck, and the government's first job is subtraction.

### 2. Champion open-source and open-weight models as strategic assets

A named priority with a geostrategic argument: open models matter "because many businesses and governments have sensitive data that they cannot send to closed model vendors," and American open models should become the global standard. Actions: improve the compute financial market, scale the NAIRR pilot, NTIA-convened SMB adoption.

### 3. Build a "try-first" culture — sandboxes over studies

"Enable AI Adoption" diagnoses the bottleneck as "limited and slow adoption… within large, established organizations," and prescribes regulatory sandboxes / AI Centers of Excellence (FDA, SEC), plus NIST-led domain efforts that "measure how much AI increases productivity at realistic tasks" — adoption measured at the task level, not the press-release level.

### 4. Worker-first framing as adoption politics

"Empower American Workers in the Age of AI": AI literacy in education/workforce funding streams, Treasury guidance making AI training tax-free under IRC §132, an AI Workforce Research Hub at DOL, rapid-retraining pilots. Strategically, this is the anti-Robodebt posture at national scale — automation sold (and built) as augmentation.

## Tactics

### 5. Build an AI evaluations ecosystem — make trust measurable

A whole named section: NIST/CAISI guidelines "for Federal agencies to conduct their own evaluations of AI systems for their distinct missions," investment in "the science of measuring and evaluating AI models," twice-yearly eval-sharing convenings, and DOE/NSF testbeds for "piloting AI systems in secure, real-world settings." Evaluations are the plan's chosen instrument for making reliability a fact rather than a claim.

### 6. Fund interpretability, control, and robustness as national capabilities

A DARPA-led program (with CAISI and NSF) on "AI interpretability, AI control systems, and adversarial robustness," plus AI hackathons to stress-test systems — the research agenda aimed squarely at the "cannot explain why a model produced a specific output" problem that blocks high-stakes deployment.

### 7. Procurement as a lever: one toolbox, ideological neutrality, model choice

"Accelerate AI Adoption in Government": a GSA/OMB **AI procurement toolbox** where "any Federal agency can easily choose among multiple models" compliant with privacy/data-governance law, with agency customization and a cross-agency use-case catalog; procurement guidelines limiting contracts to LLM developers whose systems are "objective and free from top-down ideological bias" (the Unbiased AI Principles EO); an Advanced Technology Transfer and Capability Sharing Program to move working use cases between agencies.

### 8. Secure-by-design and the full-stack infrastructure buildout

Pillar II: streamlined permitting for data centers/semiconductors/energy ("Build, Baby, Build!"), grid development, restored chip manufacturing, high-security data centers for military/IC use, an AI-infrastructure skilled-trades workforce — plus "Promote Secure-By-Design AI Technologies" and critical-infrastructure cybersecurity, so the buildout ships hardened rather than patched.

## Operations

### 9. Institutionalize coordination and talent flow

Formalize the **Chief AI Officer Council (CAIOC)** as the interagency venue (linked to CDO/CIO/Privacy councils); a Federal **talent-exchange program** for rapid details of AI specialists between agencies; mandate that "all employees whose work could benefit from access to frontier language models have access to, and appropriate training for, such tools"; an OMB-convened cohort of High Impact Service Providers piloting AI in public-facing services.

### 10. Operate incident response and evidence integrity as standing functions

"Promote Mature Federal Capacity for AI Incident Response" (Pillar II) treats AI failures as an ops discipline with playbooks, not surprises; "Combat Synthetic Media in the Legal System" hardens evidentiary rules (NIST *Guardians of Forensic Evidence* benchmark, DOJ deepfake-standard guidance) — and Pillar III extends operations outward: export the American AI stack to allies, enforce compute export controls, evaluate frontier-model national-security risks, biosecurity screening.

---

## Mapping to this project

National policy maps more loosely than the Treasury strategy, but the resonances are direct:

| # | National practice | This repo |
|---|---|---|
| 2 | Open-weight models for sensitive-data contexts | PaddleOCR open stack chosen *because* label data can't depend on a closed cloud vendor — the plan's premise-gate pivot is the policy's exact argument |
| 3 | Try-first, measured at realistic tasks | M0 measures the real task (field verification on real labels) on real hardware before scale-up |
| 5 | Evaluations ecosystem | The golden-set eval harness, FP/FN curves, and CI gates are a bureau-scale instance of the NIST evals doctrine |
| 6 | Interpretability and control | Deterministic rules engine = interpretable by construction; no black-box verdicts anywhere |
| 7 | Model choice via interface, agency customization | `Extractor` interface = procurement-toolbox thinking at code scale; engine swap without rewrite |
| 8 | Secure-by-design | Keyless, egress-free, least-surface architecture from day one — not a hardening phase |
| 9 | Access + training for all relevant staff | "Mother-proof" UI and zero-training onboarding are the bureau-level version of the access mandate |
| 10 | Incident response as ops | Error taxonomy with named recovery per stage; system errors never masquerade as compliance verdicts |
| 4 | Worker-first augmentation | Screening assistant that speeds Dave up and never overrules him — the plan's "complementing their work, not replacing it," implemented |
| 1 | Barrier removal | The wedge prototype needs no COLA authorization, no new procurement, no cloud exception — adoption with the barriers designed out |

Read alongside `treasury-ai-strategy-playbook.md`: the national plan sets the doctrine (open models, evals, try-first, worker-first), Treasury's strategy operationalizes it departmentally (federated tiers, sandbox, TCSC), and this prototype is what the doctrine looks like at the bottom of the stack — one bureau, one queue, one measured slice.
