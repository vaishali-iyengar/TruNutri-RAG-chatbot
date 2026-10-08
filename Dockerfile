# The API and chat page (implementation-plan.md, 8.5). docker-compose.yml runs it with Qdrant.
FROM python:3.12-slim

# OpenCV (used by the OCR extra) needs these shared libraries.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code changes don't reinstall them. On Linux torch comes from
# the CPU-only index (pyproject.toml), which keeps CUDA out of the image.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --extra embed --extra ocr --no-install-project

COPY . .
RUN uv sync --locked --no-dev --extra embed --extra ocr

# Bake both models and the search index into the image, so a host without a persistent
# disk (e.g. Cloud Run) starts ready. The chunks are committed, so this only embeds them;
# no API key is needed. docker-compose sets QDRANT_URL and ignores the baked index.
RUN python -c "from sentence_transformers import CrossEncoder; \
from guidance_rag.config import RetrievalConfig; CrossEncoder(RetrievalConfig().reranker_model)" \
    && python -m guidance_rag.ingest index

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", 8000)}/health')"
# Cloud Run and similar hosts pass the port in $PORT.
CMD ["sh", "-c", "exec uvicorn guidance_rag.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
