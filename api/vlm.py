"""VLM assist client (PLAN-enrichment N5 layer J3; Azure dialect = plan E1,
docs/plans/azure-enrichment-layers.md).

Providers (`LABELCHECK_VLM_PROVIDER=off|nvidia|azure`, unset ⇒ nvidia to
preserve the shipped behavior):
- nvidia — hosted Nemotron Nano VL (free developer tier). NIM dialect:
  the crop rides as an <img> data-URL inside the text content.
- azure — Azure OpenAI v1-compatible endpoint. OpenAI vision dialect:
  structured content array; both Bearer and api-key headers are sent so
  classic deployment endpoints work too.

Hard rules carried from the plan:
- Crops only — a full label never leaves the process. On this take-home the
  goldens are synthetic, but the rule is structural (sensitive-image posture).
- Suggestions never verdicts: callers attach the answer as an annotation;
  nothing in this module touches field status.
- Silent no-op: no key / unreachable / error → None, never an exception into
  a verdict path (same posture as J4's amendment, D3).
- Breaker (AD-26 shape): 3 consecutive failures → 30 s cooloff — a dead
  endpoint costs a timeout per field briefly, not per crop forever.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("uvicorn.error")

DEFAULT_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"
MAX_CROP_BYTES = 180_000        # data-URL budget; crops are small by design

BREAKER_FAILS = 3
BREAKER_COOLOFF_S = 30.0


class NanoVLClient:
    def __init__(self, api_key: str | None = None):
        self.provider = (os.environ.get("LABELCHECK_VLM_PROVIDER", "")
                         .strip().lower() or "nvidia")
        if self.provider == "azure":
            self.endpoint = os.environ.get("AZURE_VLM_ENDPOINT", "")
            self.model = os.environ.get("AZURE_VLM_MODEL", "")
            self.api_key = api_key if api_key is not None \
                else os.environ.get("AZURE_VLM_KEY", "")
        else:
            self.endpoint = os.environ.get("LABELCHECK_VLM_URL",
                                           DEFAULT_NVIDIA_ENDPOINT)
            self.model = os.environ.get("LABELCHECK_VLM_MODEL",
                                        DEFAULT_NVIDIA_MODEL)
            self.api_key = api_key if api_key is not None \
                else os.environ.get("NVIDIA_API_KEY", "")
        self._fails = 0
        self._cool_until = 0.0

    def available(self) -> bool:
        if self.provider == "off":
            return False
        if not self.api_key or not self.endpoint:
            return False
        return time.monotonic() >= self._cool_until

    def _messages(self, question: str, data_url: str) -> list[dict]:
        if self.provider == "azure":
            # OpenAI vision dialect: structured content array — the <img>
            # tag form reads as TEXT to Azure models (E1 delta #1)
            return [{"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}]
        return [{"role": "user",
                 "content": f'{question} <img src="{data_url}" />'}]

    def read_crop(self, crop_jpeg: bytes, question: str) -> str | None:
        """Ask one targeted question about one crop. Returns the answer text
        or None (silent no-op on any failure)."""
        if not self.available() or len(crop_jpeg) > MAX_CROP_BYTES:
            return None
        data_url = "data:image/jpeg;base64," + base64.b64encode(crop_jpeg).decode()
        payload = {
            "model": self.model,
            "messages": self._messages(question, data_url),
            "max_tokens": 160,
            "temperature": 0.0,
        }
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}"}
        if self.provider == "azure":
            headers["api-key"] = self.api_key      # classic deployment endpoints
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(), method="POST",
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            answer = body["choices"][0]["message"]["content"]
            self._fails = 0
            return answer.strip() or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            self._fails += 1
            if self._fails >= BREAKER_FAILS:
                self._cool_until = time.monotonic() + BREAKER_COOLOFF_S
                self._fails = 0
                log.info("VLM breaker tripped for %.0fs", BREAKER_COOLOFF_S)
            log.info("VLM assist unavailable (silent no-op): %r", e)
            return None
