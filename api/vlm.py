"""DEPRECATED (2026-08-05) — superseded by api.azure_openai.AzureVisionClient.

Kept only so the legacy `nvidia`/`azure` provider values keep working via
the factory in main.py. New code must not import NanoVLClient. The MMRead
dataclass and vision constants now live in api/azure_openai.py; the names
below re-export them for existing imports.

Original doc: VLM assist client (PLAN-enrichment N5 layer J3; Azure dialect = plan E1,
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
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("uvicorn.error")

DEFAULT_NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-nano-vl-8b-v1"
MAX_CROP_BYTES = 180_000        # data-URL budget; crops are small by design

BREAKER_FAILS = 3
BREAKER_COOLOFF_S = 30.0

# Transcription mode (mm-ocr-augment D-1). The statutory warning alone is
# ~45 words — read_crop's 160-token cap would truncate it into a false
# "differs" (eng finding F5), hence the mode-specific cap. The short
# timeout is the budget-gated-fallback contract (amendment 18): run_j3
# must be able to afford a question-mode fallback inside its 45 s job.
TRANSCRIBE_MAX_TOKENS = 600
TRANSCRIBE_TIMEOUT_S = 12
TRANSCRIBE_PROMPT = ("Transcribe every word printed in this image verbatim, "
                     "exactly as written. Output only the transcribed text — "
                     "no commentary, no translation, no corrections.")
# `unreadable` is reserved for the model SAYING it can't read (amendment
# 22's constrained contract) — matched conservatively; everything else
# that came back as text gets judged.
REFUSAL_MARKERS = ("i cannot", "i can't", "unable to", "cannot read",
                   "no text", "not legible", "illegible", "i'm sorry")


# re-exported from the successor module so existing imports keep working
from .azure_openai import MMRead  # noqa: E402,F401


class NanoVLClient:
    def __init__(self, api_key: str | None = None):
        import warnings
        warnings.warn("NanoVLClient is deprecated — use "
                      "api.azure_openai.AzureVisionClient",
                      DeprecationWarning, stacklevel=2)
        self.provider = (os.environ.get("LABELCHECK_VLM_PROVIDER", "")
                         .strip().lower() or "nvidia")
        if self.provider == "fixture":
            # keyless demo provider (mm-ocr amendment 33): transcription
            # echoes the caller-supplied expected value — keyed by field/
            # expectation, never crop bytes (crop bytes aren't stable
            # across platforms). Question mode is DISABLED under fixture
            # (read_crop → None): the shipped assist never fabricates.
            # The UI chip carries the fixture label so a leaked demo
            # config is visibly a demo (amendment 26).
            self.endpoint = "fixture"
            self.model = "fixture"
            self.api_key = "-"
        elif self.provider == "azure":
            self.endpoint = os.environ.get("AZURE_VLM_ENDPOINT", "")
            self.model = os.environ.get("AZURE_VLM_MODEL", "")
            self.api_key = api_key if api_key is not None \
                else os.environ.get("AZURE_VLM_KEY", "")
        elif self.provider == "mistral_doc":
            # Mistral Document AI on Azure Foundry (D-2, wire probed
            # 2026-08-05): POST /providers/mistral/azure/ocr, Bearer auth,
            # {"model", "document": {type: image_url, image_url: data-url}}
            # → {pages: [{markdown, ...}]}. An OCR API, not chat — so it is
            # transcription-only: question mode is disabled under it.
            self.endpoint = os.environ.get("MISTRAL_OCR_ENDPOINT", "")
            self.model = os.environ.get("MISTRAL_OCR_MODEL",
                                        "mistral-document-ai-2512")
            self.api_key = api_key if api_key is not None \
                else (os.environ.get("MISTRAL_OCR_KEY")
                      or os.environ.get("AZ_OPENAI_API_KEY", ""))
        else:
            self.endpoint = os.environ.get("LABELCHECK_VLM_URL",
                                           DEFAULT_NVIDIA_ENDPOINT)
            self.model = os.environ.get("LABELCHECK_VLM_MODEL",
                                        DEFAULT_NVIDIA_MODEL)
            self.api_key = api_key if api_key is not None \
                else os.environ.get("NVIDIA_API_KEY", "")
        # per-mode breaker (eng amendment 20): transcription failures must
        # never cool off the shipped question-mode assist. "question" is
        # the legacy mode — the _fails/_cool_until properties alias it so
        # read_crop's code path (and its tests) stay byte-identical. The
        # lock guards the NEW transcribe entries; the question path keeps
        # its shipped unguarded read-modify-write untouched on purpose.
        self._breaker_lock = threading.Lock()
        self._breaker = {"question": {"fails": 0, "cool_until": 0.0},
                         "transcribe": {"fails": 0, "cool_until": 0.0}}

    # -- legacy breaker attribute aliases (question mode) ------------------
    @property
    def _fails(self) -> int:
        return int(self._breaker["question"]["fails"])

    @_fails.setter
    def _fails(self, v: int) -> None:
        self._breaker["question"]["fails"] = v

    @property
    def _cool_until(self) -> float:
        return self._breaker["question"]["cool_until"]

    @_cool_until.setter
    def _cool_until(self, v: float) -> None:
        self._breaker["question"]["cool_until"] = v

    @property
    def engine_label(self) -> str:
        """Provenance label for suggestions/chips — derived, never
        hardcoded (fixes the 'nano-vl-8b' literal in layers, amendment 4)."""
        return self.model or self.provider

    def available(self, mode: str = "question") -> bool:
        """Default keeps the shipped semantics (question-mode breaker).
        Callers on the new path ask available("transcribe"). The chain-site
        union (amendment 20) is wired where MM_READ is known (T3/T4) —
        with MM off the transcribe breaker never trips, so today's call
        sites behave byte-identically."""
        if self.provider == "off":
            return False
        if self.provider == "fixture":
            return mode == "transcribe"    # question mode disabled under fixture
        if not self.api_key or not self.endpoint:
            return False
        if self.provider == "mistral_doc" and mode != "transcribe":
            return False                   # OCR API — no question dialect
        return time.monotonic() >= self._breaker[mode]["cool_until"]

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

    # -- transcription mode (mm-ocr-augment D-1) ---------------------------

    def _trip(self, mode: str) -> None:
        with self._breaker_lock:
            b = self._breaker[mode]
            b["fails"] += 1
            if b["fails"] >= BREAKER_FAILS:
                b["cool_until"] = time.monotonic() + BREAKER_COOLOFF_S
                b["fails"] = 0
                log.info("VLM %s breaker tripped for %.0fs", mode,
                         BREAKER_COOLOFF_S)

    def _reset(self, mode: str) -> None:
        with self._breaker_lock:
            self._breaker[mode]["fails"] = 0

    def transcribe_crop(self, crop_jpeg: bytes,
                        context: dict | None = None) -> MMRead:
        """Verbatim transcription of one crop, judged elsewhere — this
        method reports honestly and never raises. Unlike read_crop's
        silent-None posture, every failure carries a cause so the debug
        block can show WHY there is no second read (amendment 8).
        `context` ({field, expected, status}) is advisory metadata for the
        fixture provider only; real providers ignore it."""
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
        data_url = "data:image/jpeg;base64," + base64.b64encode(crop_jpeg).decode()
        if self.provider == "mistral_doc":
            payload = {"model": self.model,
                       "document": {"type": "image_url",
                                    "image_url": data_url}}
        else:
            payload = {
                "model": self.model,
                "messages": self._messages(TRANSCRIBE_PROMPT, data_url),
                "max_tokens": TRANSCRIBE_MAX_TOKENS,
                "temperature": 0.0,
            }
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}"}
        if self.provider == "azure":
            headers["api-key"] = self.api_key
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(), method="POST",
            headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TRANSCRIBE_TIMEOUT_S) as resp:
                body = json.load(resp)
        except (urllib.error.URLError, OSError, TimeoutError,
                json.JSONDecodeError) as e:
            self._trip("transcribe")
            timed_out = isinstance(e, TimeoutError) or "timed out" in str(e).lower()
            log.info("VLM transcribe failed (%s): %r",
                     "timeout" if timed_out else "transport", e)
            return MMRead("error", cause="timeout" if timed_out else "transport")
        if self.provider == "mistral_doc":
            try:
                text = "\n".join(p.get("markdown") or ""
                                 for p in body["pages"])
            except (KeyError, TypeError):
                self._trip("transcribe")
                log.info("mistral_doc schema drift: %s", str(body)[:200])
                return MMRead("error", cause="schema")
            self._reset("transcribe")
            text = text.strip()
            if not text:
                return MMRead("unreadable")
            return MMRead("ok", text=text)
        try:
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            self._trip("transcribe")
            log.info("VLM transcribe schema drift: %s", str(body)[:200])
            return MMRead("error", cause="schema")
        self._reset("transcribe")          # transport+schema succeeded
        if choice.get("finish_reason") == "length":
            # a truncated transcription must never reach the judge — it
            # would produce a false `differs` (eng finding F5 / invariant 8)
            return MMRead("error", cause="truncated")
        text = (text or "").strip()
        low = text.lower()
        if not text or any(m in low for m in REFUSAL_MARKERS):
            return MMRead("unreadable", text=text or None)
        return MMRead("ok", text=text)
