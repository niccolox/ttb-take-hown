"""The locator — the product's real engine (PLAN.md Eng Hardening: a named
component, not a bullet).

Turns OCR output (words + boxes + confidences) into located fields via
geometry-aware reading order and *targeted* fuzzy search of expected values.
Fully testable on synthetic box layouts — no OCR required.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from ..rules.normalize import loose, whitespace_only


@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    conf: float = 1.0


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def box(self) -> tuple[float, float, float, float]:
        xs1, ys1, xs2, ys2 = zip(*(w.box for w in self.words))
        return min(xs1), min(ys1), max(xs2), max(ys2)

    @property
    def min_conf(self) -> float:
        return min((w.conf for w in self.words), default=0.0)

    @property
    def y_center(self) -> float:
        b = self.box
        return (b[1] + b[3]) / 2

    @property
    def height(self) -> float:
        b = self.box
        return b[3] - b[1]


@dataclass
class LocatedField:
    found: bool
    text: str = ""
    box: tuple[float, float, float, float] | None = None
    score: float = 0.0
    runner_up: float = 0.0          # second-best score — ambiguity margin input
    min_conf: float = 0.0
    ambiguous: bool = False


AMBIGUITY_MARGIN = 5.0              # score points; closer than this → ambiguous
WARNING_ANCHOR_RE = re.compile(r"g[o0]vernment\s+warn[i1l]ng", re.I)  # OCR confusables


def union(boxes: list[tuple[float, float, float, float]]):
    xs1, ys1, xs2, ys2 = zip(*boxes)
    return min(xs1), min(ys1), max(xs2), max(ys2)


class Locator:
    def __init__(self, words: list[Word]):
        self.words = words
        self.lines = self._group_lines(words)

    # ── geometry: box → line grouping by y-overlap, x-sorted ────────────────
    @staticmethod
    def _group_lines(words: list[Word]) -> list[Line]:
        if not words:
            return []
        remaining = sorted(words, key=lambda w: ((w.box[1] + w.box[3]) / 2, w.box[0]))
        lines: list[list[Word]] = []
        for w in remaining:
            cy = (w.box[1] + w.box[3]) / 2
            h = w.box[3] - w.box[1]
            placed = False
            for line in lines:
                ly = sum((x.box[1] + x.box[3]) / 2 for x in line) / len(line)
                lh = max(x.box[3] - x.box[1] for x in line)
                if abs(cy - ly) < max(h, lh) * 0.6:
                    line.append(w)
                    placed = True
                    break
            if not placed:
                lines.append([w])
        for line in lines:
            line.sort(key=lambda w: w.box[0])
        lines.sort(key=lambda l: sum((w.box[1] + w.box[3]) / 2 for w in l) / len(l))
        return [Line(l) for l in lines]

    @property
    def full_text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    # ── targeted search: sliding token windows, incl. cross-line joins ──────
    def _windows(self, max_tokens: int):
        """Yield (text, boxes, min_conf) windows of 1..max_tokens contiguous
        words, allowing continuation across up to one adjacent line (stacked
        brand names are the NORMAL case — 'STONE'S\\nTHROW')."""
        flat: list[tuple[Word, int]] = [(w, i) for i, l in enumerate(self.lines) for w in l.words]
        n = len(flat)
        for i in range(n):
            boxes, texts, confs = [], [], []
            start_line = flat[i][1]
            for j in range(i, min(i + max_tokens, n)):
                w, ln = flat[j]
                if ln - start_line > 1:      # at most one line boundary crossed
                    break
                boxes.append(w.box)
                texts.append(w.text)
                confs.append(w.conf)
                yield " ".join(texts), list(boxes), min(confs)

    def find(self, expected: str, *, max_tokens: int | None = None,
             threshold: float = 85.0) -> LocatedField:
        """Locate `expected` via best-scoring token window; second-best score
        retained so callers can apply the ambiguity margin (Rev 2.1: a silent
        near-tie pick is never allowed)."""
        if not expected or not self.words:
            return LocatedField(found=False)
        want = loose(expected)
        span = max_tokens or (len(expected.split()) + 2)
        best = LocatedField(found=False)
        scores: list[float] = []
        for text, boxes, conf in self._windows(span):
            s = fuzz.token_sort_ratio(want, loose(text))
            scores.append(s)
            if s > best.score:
                best = LocatedField(found=s >= threshold, text=text, box=union(boxes),
                                    score=s, min_conf=conf)
        top_others = sorted((s for s in scores if s < best.score), reverse=True)
        # runner-up must come from a *different* region; approximation: next
        # distinct score value
        best.runner_up = top_others[0] if top_others else 0.0
        best.ambiguous = best.found and (best.score - best.runner_up) < AMBIGUITY_MARGIN \
            and best.runner_up >= threshold
        return best

    def find_regex(self, pattern: re.Pattern) -> LocatedField:
        """Locate the first regex hit line-by-line (ABV / net contents).
        Returns the FULL line text (not just the match span) so downstream
        parsers see co-located statements like "45% Alc./Vol. (90 Proof)"."""
        for line in self.lines:
            if pattern.search(line.text):
                return LocatedField(found=True, text=line.text, box=line.box,
                                    score=100.0, min_conf=line.min_conf)
        return LocatedField(found=False)

    # ── warning block reconstruction (anchor → grow by line adjacency) ──────
    def find_warning(self, expected_tokens: int = 44) -> LocatedField:
        anchor_idx = next((i for i, l in enumerate(self.lines)
                           if WARNING_ANCHOR_RE.search(l.text)), None)
        self._warning_block: list[Line] = []
        if anchor_idx is None:
            return LocatedField(found=False)
        block = [self.lines[anchor_idx]]
        tokens = len(block[0].text.split())
        prev = self.lines[anchor_idx]
        for line in self.lines[anchor_idx + 1:]:
            gap = line.y_center - prev.y_center
            if gap > max(prev.height, line.height) * 2.5:
                break                                   # block ended (big vertical gap)
            block.append(line)
            tokens += len(line.text.split())
            prev = line
            if tokens >= expected_tokens:
                break
        self._warning_block = block
        text = whitespace_only(" ".join(l.text for l in block))
        return LocatedField(found=True, text=text,
                            box=union([l.box for l in block]),
                            score=100.0,
                            min_conf=min(l.min_conf for l in block))

    def warning_words(self) -> list[Word]:
        """After find_warning(): the block's words in reading order — used to
        map wording-diff tokens back to image boxes for the visual diff."""
        return [w for line in getattr(self, "_warning_block", []) for w in line.words]

    def warning_prefix_body(self):
        """After find_warning(): (prefix_box, body_box) for the weight-contrast
        heuristic — prefix = the anchor's first two words ('GOVERNMENT WARNING:'),
        body = the remainder of the block. None when unavailable."""
        block = getattr(self, "_warning_block", [])
        if not block:
            return None
        first = block[0]
        prefix_words = first.words[:2]
        body_boxes = [w.box for w in first.words[2:]] +             [w.box for line in block[1:] for w in line.words]
        if not prefix_words or not body_boxes:
            return None
        return union([w.box for w in prefix_words]), union(body_boxes)
