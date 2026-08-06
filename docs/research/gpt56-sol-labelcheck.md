# GPT-5.6 "Sol" for Label Check — fit, placement, and gates

Research date: 2026-08-05. Question: should Label Check use "GPT 5.1
Sol"? **Naming untangled first:** there is no GPT-5.1 Sol. "Sol" is the
flagship variant of the **GPT-5.6 family** (released 2026-07-09; Luna <
Terra < Sol; API names `gpt-5.6-sol`, with `gpt-5.6` aliasing Sol).
GPT-5.1 is an older, separate model — and the `gpt-5.1` deployment on
niccolox-6191 is the one that rejects all operations (portal-side
deployment-kind issue, unresolved). This doc evaluates the 5.6 family,
Sol specifically, against the pipeline as it stands after the mm-ocr
work. Companions: `document-intelligence-pipeline-nemotron-openai.md`
(layer taxonomy), `docs/plans/mm-ocr-augment.md` (shipped + gated),
`azure-frontier-models.md`.

## Part 1 — What Sol is

- **Family:** GPT-5.6 (2026-07-09), three variants: **Luna** (fastest,
  cheapest — 80% price cut 2026-08-01; positioned for high-volume,
  latency-sensitive work), **Terra** (mid; 20% cut), **Sol** (flagship
  "workhorse": strongest reasoning, agentic, coding — and OpenAI's
  strongest vision model to date).
- **Sol specs:** text+image in, 1,050,000-token context, 128k output,
  knowledge cutoff 2026-02-16, **$5/M input · $30/M output**; a "Fast
  mode" offers ~2.5× throughput at a different price tier.
- **Vision quality:** best OpenAI vision yet — ~90.7% mean OCR text
  similarity on Roboflow's benchmark (GPT-5.5: 91.2%; the deltas are
  noise-level). Still **behind specialized OCR** on verbatim reading
  (GLM-OCR 94.6 on OmniDocBench; the hallucination asymmetry from the
  pipeline research still governs). Layout/document understanding is its
  standout: dense scans, forms, chart-heavy documents in one pass.

## Part 2 — Azure reality (mid-2026)

- **Available in Microsoft Foundry** as `gpt-5.6-sol/-terra/-luna`,
  preview-dated 2026-07-09, GA rolling out; Azure matches OpenAI's
  Luna/Terra price cuts from 2026-08-01.
- **Frictions:** quota is tier-gated (Tier 5/6 get default quota; lower
  tiers file a quota request), PTU region coverage is patchy, and
  MS Q&A threads report regional deployment errors for `gpt-5.6-sol`.
  Given this resource's `gpt-5.1` deployment is ALREADY broken
  portal-side, any 5.6 deployment should be created as a **standard
  chat deployment kind** and probed with the hello-world script before
  anything is wired to it.
- **Azure Government: no GPT-5.x** (Gov tops out at GPT-4.1/o3-mini per
  the prior research). Sol is commercial/demo tier only; **GPT-4.1
  remains the Gov-parity model class** for anything meant to survive
  the Government boundary story.

## Part 3 — Fit against Label Check's layers

The pipeline's division of labor (OCR grounds, multimodal transcribes,
rules judge, LLM reasons) makes the fit question per-layer, not global:

| Layer | Current engine | Sol fit | Verdict |
|---|---|---|---|
| S1 grounding OCR | Nemotron OCR v2 (local) | Wrong tool — VLMs trail specialized OCR on verbatim; no word boxes | **No** |
| mm second read (transcription, 12 s budget) | mistral_doc (gate PASSED 21/21); gpt-4.1 ready | Sol is a REASONING flagship — the Kimi lesson (hidden reasoning burns output budget, 53 s, empty text) applies to reasoning-class models generally; wrong shape for a 12 s verbatim read. **Luna** is the family's latency-sensitive variant and the only 5.6 candidate here | **No (Sol); maybe (Luna, post-eval)** |
| J3 question assist | gpt-4.1 (default) | Same reasoning/latency concern; overkill | **No** |
| **Summaries + ai_review triage (text)** | gpt-4.1 (just switched from Kimi-K2.6) | Natural upgrade path: frontier reasoning WITH a working text contract (unlike Kimi's empty-text failure). Slot is already env-shaped: `AZ_OPENAI_MODEL` + a deployment URL | **Yes — the real Sol use case, when gpt-4.1 quality proves limiting** |
| Future VLM-as-structurer (COLA-form ingestion, TODOS P2) | unbuilt | Sol's standout skill — single-pass document/layout understanding over multi-element forms | **Yes — strongest argument for Sol here** |

Cost sanity: a 512×512 crop ≈ 255 input tokens ⇒ Sol ≈ $0.0013/read
(vs gpt-4.1 ≈ $0.0005, mistral_doc $4/1k pages). Cost is not the
discriminator at screening volume; latency shape and Gov parity are.

## Part 4 — Recommendation

1. **Do not put Sol on the second-read path.** The gate just passed at
   100% precision with mistral_doc, gpt-4.1 vision is the deployed
   Gov-parity fallback, and a reasoning flagship is the wrong shape for
   a 12-second verbatim transcription (measured lesson, not prejudice).
2. **Sol's honest slots, in order:** (a) the text reasoning layers —
   summaries and ai_review triage — as a quality upgrade over gpt-4.1
   IF its drafts prove limiting (swap = `AZ_OPENAI_MODEL` + deployment
   URL, zero code); (b) the future COLA-form structurer, where its
   document understanding is the actual differentiator.
3. **If experimenting with the 5.6 family on the second read, use
   Luna** (post-price-cut, latency-positioned) and run BOTH existing
   gates before believing it: the live golden evals
   (`LABELCHECK_OPENAI_EVAL=1`) and the mm precision gate
   (`api/eval/mm_precision.py`) — the harness is already built.
4. **Deployment gates before any wiring** (the gpt-5.1 lesson):
   standard chat deployment kind, `scripts/hello_azure_openai.py`
   probe, confirm `reasoning_effort`/verbosity controls are accepted by
   the gateway (Kimi's gateway rejected them), and check quota tier.
5. **Gov posture unchanged:** GPT-4.1 stays the parity class; Sol is a
   commercial-tier enhancement, never the base story.

## Explicitly unverified

- Sol/Luna transcription latency at `reasoning_effort=minimal` on
  Azure (no public p50/p99 for small-image reads; measure, don't trust).
- Whether this subscription's quota tier gets default gpt-5.6 quota.
- Roboflow's ~90.7% is a vendor-adjacent blog benchmark — directional.
- Luna's OCR quality specifically (family benchmarks headline Sol).

Sources: openai.com/index/previewing-gpt-5-6-sol + /gpt-5-6 ·
developers.openai.com/api/docs/models/gpt-5.6-sol ·
azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry ·
ai.azure.com/catalog/models/{gpt-5.6-sol,gpt-5.1} ·
learn.microsoft.com Q&A (5.6 pricing; regional gpt-5.6-sol errors) ·
blog.roboflow.com/openai-gpt-5-6 · en.wikipedia.org/wiki/GPT-5.6 ·
edenai.co gpt-5-6-sol guide · this repo's measured lessons (Kimi
reasoning burn; gpt-5.1 deployment-kind failure; D-5 precision gate).
