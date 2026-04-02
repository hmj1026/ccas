# Stage: builder — install production dependencies
FROM python:3.12-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-editable

# Stage: dev — hot reload, source bind-mounted at runtime
FROM python:3.12-slim AS dev
RUN pip install uv
WORKDIR /app
COPY --from=builder /app/.venv ./.venv
COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "ccas.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory", "--reload"]

# Stage: production — non-root user, health check
FROM python:3.12-slim AS production
RUN groupadd -g 1001 appgroup && useradd -u 1001 -g appgroup -s /bin/sh -m appuser
RUN pip install uv
WORKDIR /app
COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv
COPY --chown=appuser:appgroup pyproject.toml uv.lock ./
COPY --chown=appuser:appgroup alembic/ ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup src/ ./src/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uv", "run", "uvicorn", "ccas.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
