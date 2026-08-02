"""Extractor interface + PaddleOCR implementation (PLAN.md: OCR behind an
`Extractor` interface so an engine swap is a drop-in, not a rewrite)."""

from __future__ import annotations

import threading
from typing import Protocol

from .locator import Word


class Extractor(Protocol):
    def extract(self, image_path: str) -> list[Word]: ...
    def ready(self) -> bool: ...


def build_extractor() -> Extractor:
    """Engine selection stays an env-var swap, not a rewrite (PLAN.md).
    LABELCHECK_EXTRACTOR=nemotron points at the GPU sidecar from
    docker-compose.gpu.yml; anything else keeps the paddle default."""
    import os

    if os.environ.get("LABELCHECK_EXTRACTOR", "paddle") == "nemotron":
        return NemotronExtractor(
            os.environ.get("NEMOTRON_OCR_URL", "http://localhost:8200"))
    return PaddleExtractor()


class PaddleExtractor:
    """Single warmed PaddleOCR instance behind a lock (M1 posture; the plan's
    measured worker pool arrives with the job API in M3 — M0 measured 2.2s/label
    on this box, so one worker meets the single-verify budget)."""

    def __init__(self) -> None:
        self._ocr = None
        self._lock = threading.Lock()
        self._ready = False

    def warm(self, sample_path: str) -> None:
        import os
        from pathlib import Path

        from paddleocr import PaddleOCR

        kwargs = dict(use_doc_orientation_classify=False, use_doc_unwarping=False,
                      use_textline_orientation=True, lang="en")
        # Offline/no-egress: paddlex's hoster lookup runs even when models are
        # cached, so point at baked local model dirs explicitly when present
        # (LABELCHECK_MODELS_DIR is set in the Docker image).
        models = os.environ.get("LABELCHECK_MODELS_DIR")
        if models and Path(models).exists():
            m = Path(models)
            missing = [n for n in ("PP-OCRv5_server_det", "en_PP-OCRv5_mobile_rec",
                                   "PP-LCNet_x1_0_textline_ori") if not (m / n).exists()]
            if missing:
                # a pin bump that changes paddle's default model set would
                # otherwise fall through to a runtime download (egress) or a
                # cryptic failure — name the problem instead
                raise RuntimeError(
                    f"LABELCHECK_MODELS_DIR={models} lacks baked models {missing}; "
                    f"rebuild the image or unset the variable")
            kwargs.update(
                text_detection_model_name="PP-OCRv5_server_det",
                text_detection_model_dir=str(m / "PP-OCRv5_server_det"),
                text_recognition_model_name="en_PP-OCRv5_mobile_rec",
                text_recognition_model_dir=str(m / "en_PP-OCRv5_mobile_rec"),
                textline_orientation_model_name="PP-LCNet_x1_0_textline_ori",
                textline_orientation_model_dir=str(m / "PP-LCNet_x1_0_textline_ori"),
            )
        with self._lock:
            self._ocr = PaddleOCR(**kwargs)
            self._ocr.predict(sample_path)          # first-inference warmup
            self._ready = True

    def ready(self) -> bool:
        return self._ready

    def extract(self, image_path: str) -> list[Word]:
        with self._lock:                            # paddle isn't safely concurrent
            pages = self._ocr.predict(image_path)
        words: list[Word] = []
        for page in pages:
            texts = page["rec_texts"]
            scores = page.get("rec_scores", [1.0] * len(texts))
            polys = page.get("rec_polys", page.get("dt_polys"))
            for text, score, poly in zip(texts, scores, polys):
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                # PaddleOCR returns line-level boxes; split into word boxes by
                # proportional width so the locator can window across tokens.
                tokens = text.split()
                if not tokens:
                    continue
                x1, x2 = float(min(xs)), float(max(xs))
                y1, y2 = float(min(ys)), float(max(ys))
                total_chars = sum(len(t) for t in tokens) + len(tokens) - 1
                cursor = x1
                for t in tokens:
                    frac = len(t) / max(1, total_chars)
                    w = (x2 - x1) * frac
                    words.append(Word(text=t, box=(cursor, y1, cursor + w, y2),
                                      conf=float(score)))
                    cursor += w + (x2 - x1) / max(1, total_chars)
        return words


class NemotronExtractor:
    """HTTP client for the Nemotron OCR v2 GPU sidecar (scripts/nemotron_server.py
    via docker-compose.gpu.yml). stdlib urllib only — the api image carries no
    requests/httpx. The sidecar already returns word-level boxes in pixel
    coords, so no proportional splitting is needed here."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._ready = False

    def warm(self, sample_path: str) -> None:
        # The sidecar loads ~2 GiB of weights after container start; poll its
        # readiness rather than racing it, then prove the wire with one extract.
        import time
        import urllib.error
        import urllib.request

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"{self._base}/v1/health/ready",
                                            timeout=5):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(3)
        else:
            raise RuntimeError(f"nemotron sidecar at {self._base} never became "
                               f"ready within 300s")
        self.extract(sample_path)
        self._ready = True

    def ready(self) -> bool:
        return self._ready

    def extract(self, image_path: str) -> list[Word]:
        import json
        import urllib.request

        with open(image_path, "rb") as f:
            req = urllib.request.Request(
                f"{self._base}/v1/ocr", data=f.read(), method="POST",
                headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
        return [Word(text=w["text"], box=tuple(w["box"]), conf=float(w["conf"]))
                for w in payload["words"] if w["text"].strip()]
