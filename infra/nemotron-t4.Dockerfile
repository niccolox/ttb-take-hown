# syntax=docker/dockerfile:1.7-labs
# Nemotron OCR v2 sidecar for ACA GPU (Consumption-GPU-NC8as-T4).
# Differences from the local dev compose build:
# - TORCH_CUDA_ARCH_LIST covers SM 7.5 (T4) alongside 8.6 (A10/RTX30xx)
# - server script and v2_english weights BAKED IN (no bind mounts in ACA)
# Build from repo root (vendor/ is dockerignored — pass it as a named
# context so the main app build context stays lean):
#   docker build -f infra/nemotron-t4.Dockerfile \
#     --build-context vendor=vendor/nemotron-ocr-v2 \
#     -t <acr>/nemotron-ocr:t4-<sha> .
FROM nvcr.io/nvidia/pytorch:25.09-py3@sha256:f3b4a33fd60d5e0358287bb44d57e91eda45e8f1681fef1bfd6c969371417130
COPY --from=vendor --exclude=.git . /workspace
WORKDIR /workspace
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -U pip hatchling "setuptools>=68" --root-user-action ignore
WORKDIR /workspace/nemotron-ocr
RUN rm -f src/nemotron_ocr_cpp/*.so || true && rm -rf build/ dist/
RUN --mount=type=cache,target=/root/.cache/pip \
    BUILD_CPP_FORCE=1 TORCH_CUDA_ARCH_LIST="7.5;8.6" ARCH=amd64 \
    pip install -v . --no-build-isolation --root-user-action ignore
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install fastapi uvicorn --root-user-action ignore
WORKDIR /workspace
COPY scripts/nemotron_server.py /workspace/nemotron_server.py
ENV NEMOTRON_MODEL_DIR=/workspace/v2_english HOME=/tmp
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "nemotron_server:app", "--host", "0.0.0.0", "--port", "8000"]
