"""Azure OpenAI / Foundry model-inference client — the third integration
client (after the OCR sidecar adapter and the VLM client), and the building
block for the J4-summary layer (docs/plans/azure-enrichment-layers.md E3).

Config (all env, read per-instance):
- AZ_GPT_4_1_URI (primary) / AZ_OPENAI_URI (fallback) — full chat-completions
  URL. Works with either surface:
    Foundry model inference:  https://<res>.services.ai.azure.com/models/chat/completions?api-version=…
    Azure OpenAI v1:          https://<res>.openai.azure.com/openai/v1/chat/completions
- AZ_GPT_4_1_KEY (primary) / AZ_OPENAI_API_KEY (fallback) — sent as BOTH
  `api-key` and `Authorization: Bearer`
  (the two surfaces prefer different headers; sending both is harmless).
- AZ_OPENAI_MODEL — deployment/model name for the request body.

Hard rules, same posture as the VLM client (D3 lineage):
- TEXT ONLY here — this client never sees an image; the summary layer's
  input is structured result JSON, never label pixels.
- Silent no-op: no key / unreachable / error → None, never an exception
  into a verdict path.
- Breaker: 3 consecutive failures → 30 s cooloff.
- Output never becomes a verdict: callers render text; nothing in this
  module touches field status (enforced at the caller by AD-41 semantics).
- Debug: OPENAI_DEBUG=true logs request/response detail (dialect, model,
  latency, sizes, truncated text, full error bodies) — the API key is
  NEVER logged in any mode. Dev flag; leave unset in shared environments
  (prompts contain application values).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("uvicorn.error")

DEFAULT_MODEL = "gpt-5.6-sol"   # user decision 2026-08-05: Sol is the default
MAX_OUTPUT_TOKENS = 2400         # summaries are short by design (plan E3) — the
                                 # ceiling leaves room for reasoning models that
                                 # think before answering (empty-output otherwise)

BREAKER_FAILS = 3
BREAKER_COOLOFF_S = 30.0

DEFAULT_API_VERSION = "2025-01-01-preview"


def _azure_chat_url(base: str, deployment: str) -> str:
    """Classic-deployment chat URL from a resource base + deployment name.
    This is what makes model switching a ONE-env-value change (audit
    2026-08-05): set AZ_BASE once; AZ_OPENAI_MODEL picks the deployment."""
    ver = os.environ.get("AZ_OPENAI_API_VERSION", DEFAULT_API_VERSION)
    return (base.rstrip("/") + f"/openai/deployments/{deployment}"
            f"/chat/completions?api-version={ver}")


class AzureOpenAIClient:
    def __init__(self, api_key: str | None = None):
        self.debug = os.environ.get("OPENAI_DEBUG", "").strip().lower() \
            in ("1", "true", "yes", "on")
        self.model = os.environ.get("AZ_OPENAI_MODEL", DEFAULT_MODEL)
        # one-value mode (audit 2026-08-05): with AZ_BASE set, the endpoint
        # is CONSTRUCTED from the model name — changing AZ_OPENAI_MODEL is
        # the whole switch. Explicit full URIs remain the legacy fallback.
        _base = os.environ.get("AZ_BASE", "").strip()
        if _base:
            self.endpoint = _azure_chat_url(_base, self.model)
        else:
            self.endpoint = os.environ.get("AZ_GPT_4_1_URI") \
                or os.environ.get("AZ_OPENAI_URI", "")
        self.api_key = api_key if api_key is not None \
            else (os.environ.get("AZ_GPT_4_1_KEY")
                  or os.environ.get("AZ_OPENAI_API_KEY", ""))
        self._fails = 0
        self._cool_until = 0.0
        # a /responses endpoint declares its dialect — skip the chat round
        # trip (the gateway-hint flip still covers gateways that route
        # chat/completions URLs to Responses)
        self._dialect = ("responses" if "/responses" in self.endpoint.split("?")[0]
                         else "chat")

    def available(self) -> bool:
        if not self.api_key or not self.endpoint:
            return False
        return time.monotonic() >= self._cool_until

    @staticmethod
    def _responses_text(body: dict) -> str:
        """Extract text from a Responses-API body (output_text, or the
        message parts inside output[])."""
        text = body.get("output_text")
        if text:
            return text
        parts = [c.get("text") for o in body.get("output", [])
                 if o.get("type") == "message"
                 for c in o.get("content", []) if c.get("type") == "output_text"]
        return " ".join(p for p in parts if p)

    def complete(self, system: str, user: str,
                 max_tokens: int = MAX_OUTPUT_TOKENS) -> str | None:
        """One chat completion. Returns the text or None (silent no-op)."""
        if not self.available():
            return None
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        cap = min(max_tokens, MAX_OUTPUT_TOKENS)
        if self._dialect == "responses":
            return self._complete_responses(messages, cap)
        payload = {"model": self.model, "messages": messages,
                   "max_tokens": cap, "temperature": 0.0}
        try:
            body = self._post(payload)
            answer = body["choices"][0]["message"]["content"]
            self._fails = 0
            self._dbg("text (%d chars): %s", len(answer or ""), (answer or "")[:200])
            return (answer or "").strip() or None
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:400]
            except OSError:
                pass
            # gpt-5.x-class chat deployments reject max_tokens in favor of
            # max_completion_tokens — adapt once
            if e.code == 400 and "max_completion_tokens" in detail:
                try:
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                    del payload["temperature"]      # 5.x chat: fixed temperature
                    body = self._post(payload)
                    answer = body["choices"][0]["message"]["content"]
                    self._fails = 0
                    return (answer or "").strip() or None
                except Exception as e2:             # noqa: BLE001 — same silent posture
                    return self._note_failure(e2)
            # Foundry gateways can route deployments to the Responses API
            # ("'messages' has moved to 'input'") — switch dialect and retry
            if e.code == 400 and "moved to 'input'" in detail:
                self._dbg("dialect flip: chat → responses (gateway hint)")
                self._dialect = "responses"
                return self._complete_responses(messages, cap)
            return self._note_failure(e, detail)
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            return self._note_failure(e)

    def _complete_responses(self, messages: list[dict], cap: int) -> str | None:
        try:
            body = self._post({"model": self.model, "input": messages,
                               "max_output_tokens": cap})
            # reasoning models can exhaust the budget mid-answer — one retry
            # with a doubled cap rather than shipping a truncated record
            if body.get("status") == "incomplete" and cap < 6000:
                self._dbg("incomplete at cap=%d — retrying with %d", cap, cap * 2)
                body = self._post({"model": self.model, "input": messages,
                                   "max_output_tokens": min(cap * 2, 6000)})
            text = self._responses_text(body)
            self._fails = 0
            self._dbg("text (%d chars): %s", len(text or ""), (text or "")[:200])
            return (text or "").strip() or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            return self._note_failure(e)

    def _dbg(self, msg: str, *args) -> None:
        if self.debug:
            log.info("[openai-debug] " + msg, *args)

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        if self.debug:
            kind = "responses" if "input" in payload else "chat"
            self._dbg("→ %s %s model=%s bytes=%d cap=%s", kind, self.endpoint,
                      payload.get("model"),
                      len(data),
                      payload.get("max_output_tokens") or
                      payload.get("max_completion_tokens") or
                      payload.get("max_tokens"))
            msgs = payload.get("messages") or payload.get("input") or []
            for m in msgs:
                c = m.get("content")
                text = c if isinstance(c, str) else json.dumps(c)
                self._dbg("  %s: %s", m.get("role"), text[:300])
        req = urllib.request.Request(
            self.endpoint, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}",
                     "api-key": self.api_key})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
        if self.debug:
            usage = body.get("usage") or {}
            self._dbg("← %d ms status=%s usage=%s",
                      round((time.monotonic() - t0) * 1000),
                      body.get("status", "ok"), json.dumps(usage)[:200])
        return body

    def _note_failure(self, e: Exception, detail: str = "") -> None:
        if self.debug:
            self._dbg("✗ %s %s", type(e).__name__, (detail or str(e))[:500])
        self._fails += 1
        if self._fails >= BREAKER_FAILS:
            self._cool_until = time.monotonic() + BREAKER_COOLOFF_S
            self._fails = 0
            log.info("Azure OpenAI breaker tripped for %.0fs", BREAKER_COOLOFF_S)
        log.info("Azure OpenAI unavailable (silent no-op): %r", e)
        return None


# ── vision (the mm second read + J3 question assist) ─────────────────────
# Successor to api/vlm.py's NanoVLClient (deprecated 2026-08-05): one
# Azure-centric vision client, default provider = the gpt-4.1 chat
# deployment (AZ_GPT_4_1_URI accepts image content arrays — same endpoint
# the text client uses, but a SEPARATE class and SEPARATE breakers: label
# pixels never meet AzureOpenAIClient, and a vision outage never cools
# the summary/triage path).
#
# Hard rules carried over verbatim: crops only (never a full label),
# 180 KB budget, suggestion-never-verdict at the callers, silent/typed
# failure posture, per-mode breakers (question vs transcribe).

MAX_CROP_BYTES = 180_000
VISION_BREAKER_FAILS = 3
VISION_BREAKER_COOLOFF_S = 30.0
TRANSCRIBE_MAX_TOKENS = 600
# gpt-5.x models spend output budget on hidden reasoning BEFORE the answer —
# measured on the Sol gate run: ~30/105 reads truncated at 600. The 5.x cap
# leaves ~600 tokens for the transcription after typical reasoning.
TRANSCRIBE_MAX_TOKENS_GPT5 = 2000      # the statutory warning alone is ~45 words
TRANSCRIBE_TIMEOUT_S = 12        # budget-gated fallback contract (run_j3)
QUESTION_MAX_TOKENS = 160
QUESTION_TIMEOUT_S = 30
TRANSCRIBE_PROMPT = ("Transcribe every word printed in this image verbatim, "
                     "exactly as written. Output only the transcribed text — "
                     "no commentary, no translation, no corrections.")
REFUSAL_MARKERS = ("i cannot", "i can't", "unable to", "cannot read",
                   "no text", "not legible", "illegible", "i'm sorry")


@dataclass
class MMRead:
    """transcribe_crop result. status: ok | unreadable | error.
    `cause` names the error class for the debug block: unconfigured |
    breaker_open | oversized | timeout | transport | schema | truncated."""
    status: str
    text: str | None = None
    cause: str | None = None


class AzureVisionClient:
    """Vision client for run_j3. Providers (LABELCHECK_VLM_PROVIDER):
    unset/gpt41 — the gpt-4.1 chat deployment (question + transcription);
    mistral_doc — Mistral Document AI OCR (transcription only);
    fixture — keyless demo (transcription only, echoes expected values);
    off — disabled. The legacy nvidia/azure values are served by the
    DEPRECATED NanoVLClient via the factory in main.py."""

    def __init__(self, api_key: str | None = None):
        raw = (os.environ.get("LABELCHECK_VLM_PROVIDER", "")
               .strip().lower() or "gpt41")
        self.provider = "gpt41" if raw in ("gpt41", "gpt-4.1",
                                           "azure_openai") else raw
        if self.provider == "fixture":
            self.endpoint = self.model = "fixture"
            self.api_key = "-"
        elif self.provider == "mistral_doc":
            self.endpoint = os.environ.get("MISTRAL_OCR_ENDPOINT", "")
            self.model = os.environ.get("MISTRAL_OCR_MODEL",
                                        "mistral-document-ai-2512")
            self.api_key = api_key if api_key is not None \
                else (os.environ.get("MISTRAL_OCR_KEY")
                      or os.environ.get("AZ_OPENAI_API_KEY", ""))
        else:                                   # gpt41 (and any unknown value)
            # LABELCHECK_VISION_MODEL overrides; otherwise the vision model
            # FOLLOWS AZ_OPENAI_MODEL — one env value switches text+vision
            self.model = (os.environ.get("LABELCHECK_VISION_MODEL")
                          or os.environ.get("AZ_OPENAI_MODEL", DEFAULT_MODEL))
            _base = os.environ.get("AZ_BASE", "").strip()
            self.endpoint = _azure_chat_url(_base, self.model) if _base \
                else os.environ.get("AZ_GPT_4_1_URI", "")
            self.api_key = api_key if api_key is not None \
                else (os.environ.get("AZ_GPT_5_1_SOL_KEY")
                      or os.environ.get("AZ_GPT_4_1_KEY")
                      or os.environ.get("AZ_OPENAI_API_KEY", ""))
        self._breaker_lock = threading.Lock()
        self._breaker = {"question": {"fails": 0, "cool_until": 0.0},
                         "transcribe": {"fails": 0, "cool_until": 0.0}}

    @property
    def engine_label(self) -> str:
        return self.model or self.provider

    def available(self, mode: str = "question") -> bool:
        if self.provider == "off":
            return False
        if self.provider == "fixture":
            return mode == "transcribe"
        if not self.api_key or not self.endpoint:
            return False
        if self.provider == "mistral_doc" and mode != "transcribe":
            return False                        # OCR API — no chat dialect
        return time.monotonic() >= self._breaker[mode]["cool_until"]

    def _trip(self, mode: str) -> None:
        with self._breaker_lock:
            b = self._breaker[mode]
            b["fails"] += 1
            if b["fails"] >= VISION_BREAKER_FAILS:
                b["cool_until"] = time.monotonic() + VISION_BREAKER_COOLOFF_S
                b["fails"] = 0
                log.info("vision %s breaker tripped for %.0fs", mode,
                         VISION_BREAKER_COOLOFF_S)

    def _reset(self, mode: str) -> None:
        with self._breaker_lock:
            self._breaker[mode]["fails"] = 0

    def _headers(self) -> dict:
        return {"Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "api-key": self.api_key}

    def _chat(self, prompt: str, data_url: str, max_tokens: int,
              timeout: float) -> dict:
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": [
                       {"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": data_url}},
                   ]}]}
        if self.model.startswith("gpt-5"):
            # 5.x chat deployments reject max_tokens and pin temperature
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
            payload["temperature"] = 0.0
        req = urllib.request.Request(self.endpoint,
                                     data=json.dumps(payload).encode(),
                                     method="POST", headers=self._headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def read_crop(self, crop_jpeg: bytes, question: str) -> str | None:
        """J3 question assist (gpt41 only). Silent-None posture."""
        if self.provider != "gpt41" or not self.available() \
                or len(crop_jpeg) > MAX_CROP_BYTES:
            return None
        data_url = "data:image/jpeg;base64," \
            + base64.b64encode(crop_jpeg).decode()
        try:
            body = self._chat(question, data_url,
                              QUESTION_MAX_TOKENS, QUESTION_TIMEOUT_S)
            answer = body["choices"][0]["message"]["content"]
            self._reset("question")
            return (answer or "").strip() or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            self._trip("question")
            log.info("vision assist unavailable (silent no-op): %r", e)
            return None

    def transcribe_crop(self, crop_jpeg: bytes,
                        context: dict | None = None) -> MMRead:
        """Verbatim transcription, judged elsewhere; typed failures."""
        if self.provider == "fixture":
            expected = (context or {}).get("expected") or ""
            return (MMRead("ok", text=str(expected)) if expected
                    else MMRead("unreadable"))
        if self.provider == "off" or not self.api_key or not self.endpoint:
            return MMRead("error", cause="unconfigured")
        if not self.available("transcribe"):
            return MMRead("error", cause="breaker_open")
        if len(crop_jpeg) > MAX_CROP_BYTES:
            return MMRead("error", cause="oversized")
        data_url = "data:image/jpeg;base64," \
            + base64.b64encode(crop_jpeg).decode()
        try:
            if self.provider == "mistral_doc":
                payload = {"model": self.model,
                           "document": {"type": "image_url",
                                        "image_url": data_url}}
                req = urllib.request.Request(
                    self.endpoint, data=json.dumps(payload).encode(),
                    method="POST", headers=self._headers())
                with urllib.request.urlopen(
                        req, timeout=TRANSCRIBE_TIMEOUT_S) as resp:
                    body = json.load(resp)
            else:
                cap = (TRANSCRIBE_MAX_TOKENS_GPT5
                       if self.model.startswith("gpt-5")
                       else TRANSCRIBE_MAX_TOKENS)
                body = self._chat(TRANSCRIBE_PROMPT, data_url,
                                  cap, TRANSCRIBE_TIMEOUT_S)
        except (urllib.error.URLError, OSError, TimeoutError,
                json.JSONDecodeError) as e:
            self._trip("transcribe")
            timed_out = isinstance(e, TimeoutError) \
                or "timed out" in str(e).lower()
            log.info("vision transcribe failed (%s): %r",
                     "timeout" if timed_out else "transport", e)
            return MMRead("error",
                          cause="timeout" if timed_out else "transport")
        if self.provider == "mistral_doc":
            try:
                text = "\n".join(p.get("markdown") or ""
                                 for p in body["pages"])
            except (KeyError, TypeError):
                self._trip("transcribe")
                log.info("mistral_doc schema drift: %s", str(body)[:200])
                return MMRead("error", cause="schema")
        else:
            try:
                choice = body["choices"][0]
                text = choice["message"]["content"]
            except (KeyError, IndexError, TypeError):
                self._trip("transcribe")
                log.info("vision transcribe schema drift: %s", str(body)[:200])
                return MMRead("error", cause="schema")
            if choice.get("finish_reason") == "length":
                self._reset("transcribe")
                log.info("vision transcribe truncated (model=%s)", self.model)
                return MMRead("error", cause="truncated")
        self._reset("transcribe")
        text = (text or "").strip()
        low = text.lower()
        if not text or any(m in low for m in REFUSAL_MARKERS):
            return MMRead("unreadable", text=text or None)
        return MMRead("ok", text=text)
