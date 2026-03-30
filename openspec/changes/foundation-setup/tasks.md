## 1. Python 後端骨架

- [ ] 1.1 建立 `backend/` 目錄，並在 `pyproject.toml` 宣告所有依賴（`fastapi`、`uvicorn`、`sqlalchemy[asyncio]`、`aiosqlite`、`alembic`、`pydantic-settings`、`pdfplumber`、`pikepdf`、`tabula-py`、`python-telegram-bot`、`google-api-python-client`、`google-auth-oauthlib`、`rq`、`redis`、`apscheduler`、`pytest`、`pytest-cov`、`pytest-asyncio`、`httpx`）
- [ ] 1.2 執行 `uv sync` 產生 `uv.lock` 並安裝依賴
- [ ] 1.3 建立 `backend/src/ccas/__init__.py` 作為根 package
- [ ] 1.4 建立包含 `__init__.py` 的模組目錄：`ingestor/`、`parser/`、`storage/`、`classifier/`、`bot/`、`api/`、`scheduler/`
- [ ] 1.5 驗證 `uv run python -c "import ccas"` 可成功執行

## 2. 應用程式設定

- [ ] 2.1 建立 `backend/src/ccas/config.py`，以 pydantic-settings 定義 `Settings` 類別（`database_url` 預設 `"sqlite+aiosqlite:///data/ccas.db"`、`telegram_bot_token`、`telegram_chat_id`、`gmail_credentials_path`、`gmail_token_path`、`log_level`、`api_host`、`api_port`、`api_token`（必填，Bearer Token 驗證用）、`redis_url` 預設 `"redis://localhost:6379/0"`），並實作動態方法 `get_pdf_password(bank_code: str) -> str | None` 從環境變數查詢銀行 PDF 密碼
- [ ] 2.2 實作有快取的單例函式 `get_settings()`
- [ ] 2.3 建立 `backend/.env.example`，列出所有設定鍵與 placeholder 值

## 3. 資料庫模型

- [ ] 3.1 建立 `backend/src/ccas/storage/database.py`，包含 SQLAlchemy engine、session factory 與 SQLite WAL mode event listener
- [ ] 3.2 在 `backend/src/ccas/storage/models.py` 建立 `Bill` model（`id`、`bank_code`、`billing_month`、`total_amount`、`due_date`、`is_paid`、`file_path`、`created_at`，以及 `bank_code+billing_month` 唯一約束）
- [ ] 3.3 新增 `Transaction` model（`id`、`bill_id` FK、`trans_date`、`posting_date`（nullable）、`merchant`、`amount`、`currency`、`original_amount`、`card_last4`、`installment_current`、`installment_total`、`category`、`note`、`created_at`）並建立與 `Bill` 的 relationship
- [ ] 3.4 新增 `Category` model（`id`、`keyword` 唯一、`category`）
- [ ] 3.5 新增 `BankConfig` model（`id`、`bank_code` 唯一、`bank_name`、`gmail_filter`、`pdf_password_rule`、`active_parser_version` 預設 `"v1"`、`is_active` 預設 `true`）

## 4. Alembic Migration

- [ ] 4.1 在 `backend/` 初始化 Alembic：`alembic init alembic`
- [ ] 4.2 設定 `alembic/env.py`，使用 Settings 提供的 database URL，並匯入 models metadata
- [ ] 4.3 產生初始 migration，建立全部 4 個資料表
- [ ] 4.4 驗證 `alembic upgrade head` 可建立資料表，且 `alembic downgrade -1` 可移除資料表

## 5. FastAPI 應用程式

- [ ] 5.1 建立 `backend/src/ccas/api/app.py`，實作 `create_app()` factory，並包含回傳 `{"status": "ok"}` 的 `/health` endpoint
- [ ] 5.2 驗證 `uv run uvicorn ccas.api.app:create_app --factory` 可在 8000 port 啟動

## 6. 後端測試基礎建設

- [ ] 6.1 在 `pyproject.toml` 設定 pytest（`testpaths` 與針對 `ccas` package 的 coverage 設定）
- [ ] 6.2 建立 `backend/tests/__init__.py`、`backend/tests/unit/__init__.py`、`backend/tests/unit/conftest.py`
- [ ] 6.3 建立 `backend/tests/integration/__init__.py`、`backend/tests/integration/conftest.py`，並提供 `db_session` fixture（in-memory SQLite、建立所有資料表、測試後 rollback）
- [ ] 6.4 撰寫 smoke test `backend/tests/integration/test_health.py`，驗證 `/health` 回傳 200 與 `{"status": "ok"}`
- [ ] 6.5 驗證 `uv run pytest` 可發現所有測試、全部通過，並產生 coverage 報告

## 7. React 前端骨架

- [ ] 7.1 建立 `frontend/` 目錄，並使用 `pnpm create vite . --template react-ts`
- [ ] 7.2 安裝並設定 Tailwind CSS
- [ ] 7.3 使用 `pnpm dlx shadcn@latest init` 初始化 shadcn/ui
- [ ] 7.4 安裝 Recharts：`pnpm add recharts`
- [ ] 7.5 建立含 health-check 訊息的 placeholder App component
- [ ] 7.6 驗證 `pnpm dev` 可在 5173 port 啟動，且 `pnpm build` 可成功執行

## 8. 前端測試基礎建設

- [ ] 8.1 安裝 vitest 與 testing-library：`pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom`
- [ ] 8.2 在 `vite.config.ts` 設定 vitest 使用 jsdom 環境
- [ ] 8.3 撰寫 smoke test `frontend/src/App.test.tsx`，驗證 App component 可正常 render
- [ ] 8.4 驗證 `pnpm test` 可發現並通過 smoke test

## 9. Seed Data

- [ ] 9.1 建立 `backend/scripts/seed.py`，包含可重複執行的範例資料（BankConfig、Category、Bill、Transaction）
- [ ] 9.2 使用 SQLAlchemy session 寫入，執行前清空已有 seed 資料以保持冪等性
- [ ] 9.3 驗證 `uv run python scripts/seed.py` 可成功執行且資料可透過 API 查詢

## 10. Docker

- [ ] 10.1 建立 `backend/Dockerfile`（Python 3.12 base、安裝 uv、複製 `pyproject.toml` + `uv.lock`、安裝依賴、複製 source code、entrypoint 為 uvicorn）
- [ ] 10.2 建立 `frontend/Dockerfile`（Node 22 base、安裝 pnpm、複製 `package.json` + `pnpm-lock.yaml`、安裝依賴、複製 source code、entrypoint 為 `vite dev --host 0.0.0.0`）
- [ ] 10.3 建立 `docker-compose.yaml`，包含 backend（port 8000、`ccas-data` volume 掛載到 `/data`）、frontend（port 5173）與 redis（port 6379、`ccas-redis` volume）三個服務
- [ ] 10.4 建立 `backend/.dockerignore` 與 `frontend/.dockerignore`
- [ ] 10.5 驗證 `docker compose up` 可啟動兩個服務，且 `localhost:8000` 可存取 `/health`
