# M2 weight-contrast heuristic — measurement notes (2026-07-31)

Method: Otsu binarize → distance-transform median stroke width; glyph height via
median connected-component height; ×4 cubic upscale below 220px region height
(JPEG-75 + 17px type flattens sub-2px stroke deltas without it); size-similarity
guard (>1.6× glyph-height difference → unknown).

Synthetic golden results (plumbing smoke — NOT validation; kill-gate requires
printed-and-photographed samples):
- clean (bold prefix / regular body): **ok** — correct
- title-case variant (bold prefix): **ok** — correct
- all-bold trap: **unknown → "confirm visually"** — conservative, safe
  (equal-weight never reads "ok"; asserting the violation stays gated)
- unit strips at 26px: bold/regular discriminated at ratio 1.43; equal-weight ~1.0-1.2

Safety property enforced in tests: equal-weight must never yield "ok".
Per-direction assertion of violations remains OFF pending real-photo validation.
