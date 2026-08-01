"""Extractor interface + PaddleOCR implementation (PLAN.md: OCR behind an
`Extractor` interface so an engine swap is a drop-in, not a rewrite)."""

from __future__ import annotations

import threading
from typing import Protocol

from .locator import Word


class Extractor(Protocol):
    def extract(self, image_path: str) -> list[Word]: ...
    def ready(self) -> bool: ...


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
