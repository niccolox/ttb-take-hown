# Enabling the multimodal second read (MM)

Operational guide, 2026-08-05. MM = **m**ulti**m**odal second read: rows
that settle troubled (NEEDS_REVIEW, or MISMATCH when the layer is on)
get a verbatim re-read of their evidence crop by a vision model, judged
**deterministically** by `api/mm_judge.py` — the model contributes eyes,
the rules engine contributes the verdict, and no field status ever
changes. Plan: `docs/plans/mm-ocr-augment.md` (approved /autoplan review
+ measured D-0 value gate). Vision client: `api/azure_openai.py` `AzureVisionClient` (api/vlm.py
is deprecated). Provider-neutral successor to
`docs/enable-azure-vlm.md` (which covers the Azure specifics of the J3
question assist; still valid for those).

## 60-second keyless demo (no credentials, no network)

```bash
LABELCHECK_MM_READ=1 LABELCHECK_VLM_PROVIDER=fixture \
  docker compose -f docker-compose.dev.yml up --force-recreate
```

Open http://localhost:8123, load the built-in sample **“Bad photo →
human review”**, verify it, and wait for the cross-check to settle
(~seconds). Expect: a **“Second read: agrees”** chip on the Class/type
row, carrying a **“fixture demo”** badge (canned transcriptions — the
fixture echoes expected values so you can see the plumbing without a
key; chips are visibly demos, and the shipped question assist is
disabled under fixture so nothing real is fabricated). Trap samples
(e.g. *Titlecase warning*) demo the amber **“sides with the
application”** chip.

Flags are read at **process start** — compose users need
`--force-recreate` after changing them.

## Startup signal — verify it's on / it's broken

With `LABELCHECK_MM_READ` set, the server logs ONE line at boot:

```
mm second read: enabled provider=azure key=present
mm second read: enabled provider=azure key=ABSENT — layer INACTIVE
```

No line ⇒ the flag isn't set (feature off). `key=ABSENT — layer
INACTIVE` ⇒ misconfiguration — fix the provider's key env. Per-row
outcomes (including error causes like `timeout`, `schema`,
`breaker_open`) appear in each row's **Second-read debug** details
block in the UI. The transcription breaker is per-mode: three failures
cool the second read for 30 s WITHOUT touching the question assist.

## The flag matrix

`LABELCHECK_MM_READ` (default **off**) gates the second read.
`LABELCHECK_VLM_PROVIDER` is the ONE provider knob (it also drives the
shipped J3 question assist).

| MM_READ | PROVIDER | key | What you get |
|---|---|---|---|
| unset | any | any | Byte-identical shipped behavior; zero transcription egress |
| set | unset ⇒ `gpt41` | absent | Zero egress entirely; startup line says INACTIVE |
| set | unset ⇒ `gpt41` | `AZ_GPT_4_1_URI`+`AZ_GPT_4_1_KEY` | **Default:** second read + question assist via the gpt-4.1 chat deployment (image content arrays on the same endpoint; Gov-parity model class, vision-input parity in Gov unverified) |
| set | `nvidia` / `azure` | (legacy vars) | DEPRECATED — still honored via the old NanoVLClient with a startup warning; migrate to the default or mistral_doc |
| set | `mistral_doc` | `MISTRAL_OCR_ENDPOINT` (+`MISTRAL_OCR_KEY`, falls back to `AZ_OPENAI_API_KEY`) | Second read via Mistral Document AI on Foundry (transcription-only — question assist off; wire probed live 2026-08-05, `mistral-document-ai-2512`) |
| set | `fixture` | none | Keyless demo: canned transcriptions, question mode disabled, chips badged |
| set | `off` | any | Everything off — `off` beats `MM_READ` |
| unset | `fixture` | none | Nothing (fixture is transcription-only and the flag is off) |

**One-value model switch (audit 2026-08-05):** with `AZ_BASE` set once,
`AZ_OPENAI_MODEL` selects the Azure deployment for the text layers AND
the vision second read (endpoints are constructed; the resource key is
shared). `LABELCHECK_VISION_MODEL` overrides vision separately. Live-
verified with `gpt-5.6-sol` (the DEFAULT model): 2.9 s crop
transcription, judge agrees; gpt-5.x transcriptions run with a 2000-token
cap (reasoning headroom — the 600 cap truncated ~30/105 reads on the
gate run).
Note the Gov caveat: no GPT-5.x in Azure Government — pin
`LABELCHECK_VISION_MODEL=gpt-4.1` for Gov-parity work.

Rollback is env-only: unset `LABELCHECK_MM_READ`, `--force-recreate`.
Old results render unchanged (rows without `mm_reread` show no chip).

## Verdict semantics (why "differs" is quiet)

The second reader is statistically weaker than the primary OCR on exact
text, so raw disagreement is noise. Headline chips: **agrees** (the
transcription supports the expected reading) and **sides with the
application** (MISMATCH row where the transcription contains the
applicant's value — the one actionable disagreement, amber). Plain
`differs`, `unreadable`, and `error(cause)` live only in the debug
block. The warning field is judged on **content words only** —
typography/weight-contrast checks are not attestable from a
transcription and keep their S2 verdicts.

## Evals and the ship gate

```bash
# fast tier (rides make test — hermetic, no network):
.venv/bin/pytest api/tests/test_mm_reread.py api/tests/test_mm_flags.py \
    api/tests/test_mm_traps.py api/tests/test_transcribe_mode.py -q

# D-0 incidence measurement (server up):
.venv/bin/python api/eval/measure_troubled.py

# live precision ship-gate (server up, MM on, REAL provider):
LABELCHECK_MM_READ=1 .venv/bin/python api/eval/mm_precision.py
```

The chip may not default on in any deployment until the precision gate
passes: `sides_with_application` precision ≥ 80% with n ≥ 10, measured
with the calibration (COLA Cloud) / held-out (golden traps) split.
Until a real vision provider is deployed the gate trivially fails —
that is the intended posture.

## Data governance

Crops only — a full label never leaves the process. Flags default off
everywhere; stage/prod stay off until the model-placement standard
clears a vision model for pre-approval images (see
`docs/plans/azure-enrichment-layers.md`). PRC-origin models are
excluded from image paths per the repo's supply-chain posture.
