# The Mother Test — Unaided First-Use Protocol (train-before-pilot T5)

Purpose: evidence that the training burden approaches zero — the
pilot-gate artifact mapping tool features onto the Treasury AI Strategy's
training requirement (docs/research/train-before-pilot.md).

## Protocol (3 participants, ~15 minutes each)

1. **Recruit** three people who have never seen the tool and are not
   software engineers. (The archetype: your mother. TTB domain knowledge
   is a bonus, not a requirement.)
2. **Hand over exactly one sentence:** "This tool checks alcohol label
   images against their applications — try it." Give the URL. Nothing else:
   no demo, no vocabulary, no pointing.
3. **Observe silently.** Note: did they find the walk-through or a sample
   unaided? Did they reach a settled result? Did they record a decision?
   Where did they hesitate longer than ~10 seconds, and what were they
   looking at?
4. **Afterwards, ask three questions:**
   - "What does this tool do, in your words?" (pass: screening + the
     human decides — if they say "it approves labels," the UI has failed
     the no-authority message)
   - "What did the amber result want from you?"
   - "What would you do next with a real stack of labels?"
5. **Record** per participant: unaided completion (yes/no), time to first
   decision (the tool logs it locally — E4 stream, `kind: "ui"`),
   walk-through completed (also logged), hesitation points, quotes.

## Pass criteria

- 3/3 reach a settled result unaided; ≥2/3 record a defensible decision.
- 0/3 describe the tool as deciding/approving on its own.
- Every hesitation point becomes a UI fix or a runbook line — the
  protocol's output is a work list, not a grade.

## Telemetry fields (local only, no egress)

- `{"kind":"ui","event":"tour_started"}` / `"tour_completed"` (+ms)
- `{"kind":"ui","event":"first_decision","ms":…}` — first item added →
  first recorded decision (field or whole-label).
