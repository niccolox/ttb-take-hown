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
MAX_OUTPUT_TOKENS = 700          # summaries are short by design (plan E3)

BREAKER_FAILS = 3
BREAKER_COOLOFF_S = 30.0


class AzureOpenAIClient:
    def __init__(self, api_key: str | None = None):
        self.endpoint = os.environ.get("AZ_OPENAI_URI", "")
        self.model = os.environ.get("AZ_OPENAI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key if api_key is not None \
            else os.environ.get("AZ_OPENAI_API_KEY", "")
        self._fails = 0
        self._cool_until = 0.0

    def available(self) -> bool:
        if not self.api_key or not self.endpoint:
            return False
        return time.monotonic() >= self._cool_until

    def complete(self, system: str, user: str,
                 max_tokens: int = MAX_OUTPUT_TOKENS) -> str | None:
        """One chat completion. Returns the text or None (silent no-op)."""
        if not self.available():
            return None
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": min(max_tokens, MAX_OUTPUT_TOKENS),
            "temperature": 0.0,
        }
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}",
                     "api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            answer = body["choices"][0]["message"]["content"]
            self._fails = 0
            return (answer or "").strip() or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            self._fails += 1
            if self._fails >= BREAKER_FAILS:
                self._cool_until = time.monotonic() + BREAKER_COOLOFF_S
                self._fails = 0
                log.info("Azure OpenAI breaker tripped for %.0fs", BREAKER_COOLOFF_S)
            log.info("Azure OpenAI unavailable (silent no-op): %r", e)
            return None
