# Stage: uv — single source for the uv binary (pinned)
FROM ghcr.io/astral-sh/uv:0.10 AS uv

# Stage: builder — install production dependencies
FROM python:3.12-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
# ``fubon-llm`` extra installs the ``anthropic`` SDK so the documented
# ``FUBON_CAPTCHA_FALLBACK_LLM=true`` recovery path is actually functional
# in the stock production image. Without it, enabling the flag would
# surface ``llm_fallback_unavailable`` at runtime (fail-loud) instead of
# silently degrading to OCR-only.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-editable --extra fubon-llm
# ddddocr ships its ONNX models inside the wheel (~76 MB), so no remote
# preload is required at build time — the prior EasyOCR preload step was
# removed via fix-fubon-captcha-solver-accuracy.

# Stage: dev — hot reload, source bind-mounted at runtime
FROM python:3.12-slim AS dev
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-tra fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --group dev
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "ccas.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory", "--reload"]

# Stage: production — non-root user, health check
FROM python:3.12-slim AS production
LABEL org.opencontainers.image.title="ccas-backend" \
      org.opencontainers.image.description="CCAS Backend API, worker, scheduler, and bot"
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-tra fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 1001 appgroup && useradd -u 1001 -g appgroup -s /bin/sh -m appuser
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv
COPY --chown=appuser:appgroup pyproject.toml uv.lock ./
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup src/ ./src/
RUN mkdir -p /data /logs && chown appuser:appgroup /data /logs
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uv", "run", "uvicorn", "ccas.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
