# Label Check — single image: FastAPI + PaddleOCR (CPU) + static UI.
# Models are baked at build (no runtime downloads — the no-egress/firewall story).
# Base pinned by DIGEST (800-190 re-audit: mutable tags were the last open
# container finding) — the tag stays as a human-readable comment. Bump ritual:
#   docker buildx imagetools inspect python:3.12-slim   → update digest,
#   rebuild, run the suite + golden sweep (same ritual as the dependency lock).
# python:3.12-slim as of 2026-08-03:
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libglib2.0-0 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Hash-locked install (TODOS P1): pip refuses any artifact whose SHA-256
# isn't in the lock — a hijacked PyPI release fails the build. Regenerate:
#   uv pip compile api/requirements.in --generate-hashes -o api/requirements.lock
COPY api/requirements.lock api/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r api/requirements.lock

# Non-root runtime (audit F2, 800-190): uid 1000 matches the host bind-mount
# owner in the dev composes, so ./api/data stays writable in both worlds.
RUN useradd -m -u 1000 app

COPY api/ api/
COPY scripts/ scripts/
COPY Makefile .

# Bake OCR models into the image AS THE APP USER (they land under
# /home/app/.paddlex): trigger the official-model download once at build
# time so container start needs zero egress and warmup is fast.
USER app
RUN python - <<'EOF'
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=True, lang="en")
ocr.predict("api/eval/golden/spirits_clean.jpg")
print("models baked")
EOF

# Supply-chain gate (TODOS P1): the bake above downloads weights from Baidu's
# CDN with no integrity guarantee — assert them against the committed
# known-good manifest; a drifted upstream fails the BUILD, not production.
RUN python -m api.integrity check --models-dir /home/app/.paddlex/official_models

ENV PORT=8123 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True LABELCHECK_MODELS_DIR=/home/app/.paddlex/official_models
EXPOSE 8123
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=6 \
    CMD curl -sf http://localhost:8123/healthz | grep -q '"ready":true' || exit 1
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
