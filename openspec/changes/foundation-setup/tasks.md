## 1. Python Backend Scaffold

- [ ] 1.1 Create `backend/` directory with `pyproject.toml` declaring all dependencies (fastapi, uvicorn, sqlalchemy, alembic, pydantic-settings, pdfplumber, pikepdf, tabula-py, python-telegram-bot, google-api-python-client, apscheduler, pytest, pytest-cov, httpx)
- [ ] 1.2 Run `uv sync` to generate `uv.lock` and install dependencies
- [ ] 1.3 Create `backend/src/ccas/__init__.py` as the root package
- [ ] 1.4 Create module directories with `__init__.py`: `ingestor/`, `parser/`, `storage/`, `classifier/`, `bot/`, `api/`, `scheduler/`
- [ ] 1.5 Verify `uv run python -c "import ccas"` succeeds

## 2. App Configuration

- [ ] 2.1 Create `backend/src/ccas/config.py` with pydantic-settings `Settings` class (database_url, telegram_bot_token, telegram_chat_id, gmail_credentials_path, gmail_token_path, log_level, api_host, api_port)
- [ ] 2.2 Implement `get_settings()` cached singleton function
- [ ] 2.3 Create `backend/.env.example` with all config keys and placeholder values

## 3. Database Models

- [ ] 3.1 Create `backend/src/ccas/storage/database.py` with SQLAlchemy engine, session factory, and SQLite WAL mode event listener
- [ ] 3.2 Create `backend/src/ccas/storage/models.py` with `Bill` model (id, bank_code, billing_month, total_amount, due_date, is_paid, file_path, created_at, unique constraint on bank_code+billing_month)
- [ ] 3.3 Add `Transaction` model (id, bill_id FK, trans_date, merchant, amount, currency, original_amount, card_last4, installment_current, installment_total, category, note, created_at) with relationship to Bill
- [ ] 3.4 Add `Category` model (id, keyword unique, category)
- [ ] 3.5 Add `BankConfig` model (id, bank_code unique, bank_name, gmail_filter, pdf_password_rule, active_parser_version default "v1")

## 4. Alembic Migrations

- [ ] 4.1 Initialize Alembic in `backend/` with `alembic init alembic`
- [ ] 4.2 Configure `alembic/env.py` to use Settings for database URL and import models metadata
- [ ] 4.3 Generate initial migration creating all 4 tables
- [ ] 4.4 Verify `alembic upgrade head` creates tables and `alembic downgrade -1` drops them

## 5. FastAPI App

- [ ] 5.1 Create `backend/src/ccas/api/app.py` with `create_app()` factory that includes a `/health` endpoint returning `{"status": "ok"}`
- [ ] 5.2 Verify `uv run uvicorn ccas.api.app:create_app --factory` starts on port 8000

## 6. Backend Test Infrastructure

- [ ] 6.1 Configure pytest in `pyproject.toml` (testpaths, coverage settings targeting ccas package)
- [ ] 6.2 Create `backend/tests/__init__.py`, `backend/tests/unit/__init__.py`, `backend/tests/unit/conftest.py`
- [ ] 6.3 Create `backend/tests/integration/__init__.py`, `backend/tests/integration/conftest.py` with `db_session` fixture (in-memory SQLite, create all tables, rollback after test)
- [ ] 6.4 Write smoke test `backend/tests/integration/test_health.py` verifying `/health` returns 200 and `{"status": "ok"}`
- [ ] 6.5 Verify `uv run pytest` discovers and passes all tests with coverage report

## 7. React Frontend Scaffold

- [ ] 7.1 Create `frontend/` directory with `pnpm create vite . --template react-ts`
- [ ] 7.2 Install and configure Tailwind CSS
- [ ] 7.3 Initialize shadcn/ui with `pnpm dlx shadcn@latest init`
- [ ] 7.4 Install Recharts: `pnpm add recharts`
- [ ] 7.5 Create placeholder App component with health-check message
- [ ] 7.6 Verify `pnpm dev` starts on port 5173 and `pnpm build` succeeds

## 8. Frontend Test Infrastructure

- [ ] 8.1 Install vitest and testing-library: `pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom`
- [ ] 8.2 Configure vitest in `vite.config.ts` with jsdom environment
- [ ] 8.3 Write smoke test `frontend/src/App.test.tsx` verifying App component renders
- [ ] 8.4 Verify `pnpm test` discovers and passes the smoke test

## 9. Docker

- [ ] 9.1 Create `backend/Dockerfile` (Python 3.12 base, install uv, copy pyproject.toml + uv.lock, install deps, copy src, entrypoint: uvicorn)
- [ ] 9.2 Create `frontend/Dockerfile` (Node 22 base, install pnpm, copy package.json + pnpm-lock.yaml, install deps, copy src, entrypoint: vite dev --host 0.0.0.0)
- [ ] 9.3 Create `docker-compose.yaml` with backend (port 8000, ccas-data volume at /data) and frontend (port 5173) services
- [ ] 9.4 Create `backend/.dockerignore` and `frontend/.dockerignore`
- [ ] 9.5 Verify `docker compose up` starts both services and `/health` is reachable at localhost:8000
