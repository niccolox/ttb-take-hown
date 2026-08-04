"""Azure OpenAI / Foundry model-inference client — the third integration
client (after the OCR sidecar adapter and the VLM client), and the building
block for the J4-summary layer (docs/plans/azure-enrichment-layers.md E3).

Config (all env, read per-instance):
- AZ_OPENAI_URI   — full chat-completions URL. Works with either surface:
    Foundry model inference:  https://<res>.services.ai.azure.com/models/chat/completions?api-version=…
    Azure OpenAI v1:          https://<res>.openai.azure.com/openai/v1/chat/completions
- AZ_OPENAI_API_KEY — sent as BOTH `api-key` and `Authorization: Bearer`
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

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("uvicorn.error")

DEFAULT_MODEL = "gpt-4.1"
MAX_OUTPUT_TOKENS = 2400         # summaries are short by design (plan E3) — the
                                 # ceiling leaves room for reasoning models that
                                 # think before answering (empty-output otherwise)

BREAKER_FAILS = 3
BREAKER_COOLOFF_S = 30.0


class AzureOpenAIClient:
    def __init__(self, api_key: str | None = None):
        self.debug = os.environ.get("OPENAI_DEBUG", "").strip().lower() \
            in ("1", "true", "yes", "on")
        self.endpoint = os.environ.get("AZ_OPENAI_URI", "")
        self.model = os.environ.get("AZ_OPENAI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key if api_key is not None \
            else os.environ.get("AZ_OPENAI_API_KEY", "")
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
