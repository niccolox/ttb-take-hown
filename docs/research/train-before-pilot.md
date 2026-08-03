# Train Before Pilot — Treasury AI Strategy × Label Check (2026-08-03)

Sources (fetched 2026-08-03):
- Treasury AI Strategy (home.treasury.gov/system/files/136/Treasury-AI-Strategy.pdf,
  Dec 2025 revision) — the department's enterprise AI posture
- Treasury AI Compliance Plan (same library) — OMB-directed governance
- Press: Treasury AI Innovation Series launch/conclusion (sb0421, sb0540)

## What the strategy actually says (relevant passages)

1. **Training precedes use, by policy.** For the department's own AI chat
   pilot: *"All employees are required to complete training to ensure
   compliance with Treasury's AI acceptable use policy."* Training is a
   hard gate in front of every pilot seat.
2. **Pilots are learning instruments.** Pilot programs are *"designed to
   build experience, refine internal controls, and inform broader
   implementation"* — a pilot's output is evidence, not just usage.
3. **AI-Ready Workforce pillar.** Fluency across roles, training
   *"tailored to meet the needs of different roles and skill levels"*,
   hands-on learning (AI Innovation Center) over classroom abstraction.
4. **Federated governance.** High-impact use cases go to the AI
   Governance Board; **moderate/low use cases are bureau-managed** with
   approved tools, safety standards, and data-security adherence —
   reported through the AI Council.

## The thesis

"Train before pilot" is normally read as a cost: build a course, schedule
sessions, then pilot. The inversion: **make the tool itself the
training.** If the UI is self-evident ("mother-proof"), the runbook is
one page, and a guided sample walk-through is built into the product,
then the role-tailored, hands-on training the strategy demands is
delivered *by the pilot artifact itself* — the marginal training burden
approaches zero, and the compliance gate (item 1) is satisfied with a
walkthrough completion instead of a course completion.

Label Check is well positioned: a screening aid with human decision
primacy is a **moderate/low use case** under the federated model (item
4), and much of the "mother-proofing" already shipped — COLAs-native
status vocabulary (Received / In Process / Needs Correction: an agent's
existing mental model IS the training), the empty-state hero, the earned
PASS lock with its 🔒 explanation, teaching notes on NOT_CHECKED fields,
plain-language banners, and the journey stepper that narrates the
pipeline without jargon.

## Implementation plan

**T1 · In-app sample walk-through ("First check in 90 seconds").**
A guided mode launched from the empty-state hero and the footer: loads a
golden sample, runs a real check, and steps through five positioned
callouts — journey stepper → field rows + evidence crops → an amber row
and its per-field decision buttons → the whole-label decision (and why
PASS is locked until rows resolve) → export/save. No library: a small
vendored overlay (sequence of anchored tooltips, Next/Done), driven by
the existing sample flow; deterministic because the golden's outcome is
known, so the narration can be exact. *Acceptance: from a cold load, an
untrained user reaches a recorded decision unaided.*

**T2 · Agent runbook (one page, lives in the app).**
docs/runbook.md, printable, served via a footer link: what the tool is
and is not (screens; the agent decides — no approval authority), the
six-step workflow (add → statuses → review ambers → decide rows → decide
label → export), the status vocabulary table, how to read an evidence
crop and a diff box, what NEEDS_REVIEW means (honest uncertainty, not
failure), and the known limits (type size/placement not fully checked).
One page is a design constraint, not a summary: if it doesn't fit, the
UI has a defect to fix instead.

**T3 · Mother-proof audit (plain-language pass).**
A zero-jargon sweep of every user-visible string against a reading-level
target; engineering words that remain ("cross-checking", "provisional")
get introduced once by the T1 tour and nowhere else. Every dead end must
name its next step (the NOT_CHECKED teaching notes and the export guard
are the pattern). Deliverable: a short findings list, fixed in place.

**T4 · Training corpus (curated lesson set).**
A "Training set" group in the Eval sets menu: five labels, one lesson
each — clean pass; amber needs-review and how to decide it; a planted
trap red and what correction looks like; a front+back pair (warning on
the back); a degraded photo landing an honest amber. The SAMPLES
`shows` field already carries per-item lesson text — this is curation
plus a menu group, not new machinery.

**T5 · Measure the burden (pilot-gate evidence).**
Instrument time-to-first-decision and walk-through completion in the
local telemetry stream (E4 pattern — no egress), and document a
three-person hallway protocol (the "mother test"): hand over the URL,
no instructions, record unaided completion. Output feeds a one-page
pilot memo mapping tool artifacts onto the strategy's requirements:
walkthrough completion ↔ training gate; runbook + AI risk statement +
DevSecOps docs ↔ bureau-managed safeguards evidence; telemetry ↔ the
"pilots build experience and refine controls" expectation.

## Sequencing and cost

T2 (runbook) and T4 (training corpus) are hours — mostly writing and
curation against existing machinery. T1 (tour) is the only real build:
one overlay component, one scripted sequence, cache-busted like every
UI change. T3 rides along as review. T5 is a telemetry field plus a
protocol page. Nothing requires new services, models, or egress — the
no-egress and no-approval-authority premises are untouched.

## What already counts (no work needed)

COLAs-native vocabulary · empty-state hero with the two obvious actions ·
journey stepper naming each stage in agent language · earned-PASS lock
with explanation · per-field teaching notes (§4.36 blank-value guidance,
molded-container carve-outs) · evidence crops with diff boxes · honest
NEEDS_REVIEW doctrine (the tool never bluffs, so trust doesn't need to
be taught) · footer references linking the governing TTB guidance.
