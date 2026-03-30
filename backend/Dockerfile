FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-editable

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "ccas.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
