# Label Check — single image: FastAPI + PaddleOCR (CPU) + static UI.
# Models are baked at build (no runtime downloads — the no-egress/firewall story).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libglib2.0-0 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt \
        fastapi uvicorn python-multipart

COPY api/ api/
COPY scripts/ scripts/
COPY Makefile .

# Bake OCR models into the image: trigger the official-model download once at
# build time so container start needs zero egress and warmup is fast.
RUN python - <<'EOF'
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=True, lang="en")
ocr.predict("api/eval/golden/spirits_clean.jpg")
print("models baked")
EOF

ENV PORT=8123 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True LABELCHECK_MODELS_DIR=/root/.paddlex/official_models
EXPOSE 8123
HEALTHCHECK --interval=10s --timeout=3s --start-period=60s --retries=6 \
    CMD curl -sf http://localhost:8123/healthz | grep -q '"ready":true' || exit 1
CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
