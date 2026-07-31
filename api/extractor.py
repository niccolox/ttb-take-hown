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
        from paddleocr import PaddleOCR
        with self._lock:
            self._ocr = PaddleOCR(use_doc_orientation_classify=False,
                                  use_doc_unwarping=False,
                                  use_textline_orientation=True, lang="en")
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
