"""Nano VL assist client (PLAN-enrichment N5, layer J3).

Model: Llama-3.1-Nemotron-Nano-VL-8B-V1 — the clean-lineage pick from
docs/research/document-intelligence-pipeline-nano-vl-azure.md. Dev path is
NVIDIA's hosted endpoint (free Developer tier, rate-limited); production
co-locates the open weights beside the OCR sidecar on an A10.

Hard rules carried from the plan:
- Crops only — a full label never leaves the process. On this take-home the
  goldens are synthetic, but the rule is structural (sensitive-image posture).
- Suggestions never verdicts: callers attach the answer as an annotation;
  nothing in this module touches field status.
- Silent no-op: no key / unreachable / error → None, never an exception into
  a verdict path (same posture as J4's amendment, D3).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("uvicorn.error")

ENDPOINT = os.environ.get(
    "LABELCHECK_VLM_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
MODEL = os.environ.get(
    "LABELCHECK_VLM_MODEL", "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")
MAX_CROP_BYTES = 180_000        # data-URL budget; crops are small by design


class NanoVLClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key if api_key is not None \
            else os.environ.get("NVIDIA_API_KEY", "")

    def available(self) -> bool:
        return bool(self.api_key)

    def read_crop(self, crop_jpeg: bytes, question: str) -> str | None:
        """Ask one targeted question about one crop. Returns the answer text
        or None (silent no-op on any failure)."""
        if not self.available() or len(crop_jpeg) > MAX_CROP_BYTES:
            return None
        data_url = "data:image/jpeg;base64," + base64.b64encode(crop_jpeg).decode()
        payload = {
            "model": MODEL,
            "messages": [{
                "role": "user",
                "content": f'{question} <img src="{data_url}" />',
            }],
            "max_tokens": 160,
            "temperature": 0.0,
        }
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.load(resp)
            answer = body["choices"][0]["message"]["content"]
            return answer.strip() or None
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                json.JSONDecodeError, TimeoutError) as e:
            log.info("VLM assist unavailable (silent no-op): %r", e)
            return None
