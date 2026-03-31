# test-infrastructure Specification

## Purpose
TBD - created by archiving change foundation-setup. Update Purpose after archive.
## Requirements
### Requirement: 後端 pytest 設定
系統 SHALL 透過 `pyproject.toml` 設定 pytest，並將測試目錄設為 `backend/tests/unit/` 與 `backend/tests/integration/`。coverage 報告 SHALL 針對 `ccas` package 啟用，且最低門檻為 80%。

#### Scenario: pytest 可發現並執行測試
- **WHEN** 在 `backend/` 目錄執行 `uv run pytest`
- **THEN** pytest 會找到 `tests/unit/` 與 `tests/integration/` 下的測試並執行

#### Scenario: 產生 coverage 報告
- **WHEN** 執行 `uv run pytest --cov=ccas --cov-report=term-missing`
- **THEN** 會顯示涵蓋 `ccas` 所有模組逐行資訊的 coverage 報告

### Requirement: 後端測試目錄結構
系統 SHALL 將後端測試分為 `tests/unit/`（純單元測試，不接資料庫或外部服務）與 `tests/integration/`（含資料庫 fixture 的測試）。每個測試目錄 SHALL 都包含 `__init__.py` 與 `conftest.py`。

#### Scenario: 單元測試目錄存在且包含 conftest
- **WHEN** 專案完成初始化
- **THEN** `backend/tests/unit/conftest.py` 存在，且可被 import

#### Scenario: 整合測試目錄存在且包含 conftest
- **WHEN** 專案完成初始化
- **THEN** `backend/tests/integration/conftest.py` 存在，且可被 import

### Requirement: 提供整合測試資料庫 fixture（Async）
整合測試的 `conftest.py` SHALL 提供 `db_session` fixture（異步 fixture），使用 pytest-asyncio。該 fixture 應：
1. 建立 in-memory async SQLite engine（`create_async_engine("sqlite+aiosqlite:///:memory:")`）
2. 執行 Alembic migration（需兼容 async engine）
3. Yield 一個 async SQLAlchemy session（使用 `async_sessionmaker`）
4. 在每個測試結束後 rollback transaction

#### Scenario: 整合測試取得乾淨資料庫
- **WHEN** 某個異步整合測試使用 `db_session` fixture
- **THEN** 該測試會取得包含所有資料表的全新 in-memory async database，且測試變更在結束後會回滾

#### Scenario: 支援異步查詢
- **WHEN** 測試中透過 `async with db_session.begin()` 執行查詢
- **THEN** 所有 query 都可透過 `await` 執行，不會阻塞 event loop

### Requirement: 提供後端 health endpoint smoke test
系統 SHALL 包含一個 smoke test，驗證 FastAPI `/health` 端點回傳 200 與 `{"status": "ok"}`。

#### Scenario: Health endpoint 測試通過
- **WHEN** 執行 `uv run pytest tests/integration/test_health.py`
- **THEN** 該測試會通過，證明 health endpoint 可正常運作

### Requirement: 前端 vitest 設定
系統 SHALL 透過 `vite.config.ts` 為前端設定 vitest。測試檔命名 SHALL 採用 `*.test.tsx` 或 `*.test.ts`。

#### Scenario: vitest 可發現並執行測試
- **WHEN** 在 `frontend/` 目錄執行 `pnpm test`
- **THEN** vitest 會找到並執行所有符合命名慣例的測試檔

### Requirement: 提供前端 smoke test
系統 SHALL 包含一個 smoke test，驗證 React App component 可正常 render。

#### Scenario: App 元件 render 測試通過
- **WHEN** 執行 `pnpm test`
- **THEN** smoke test 會通過，證明 App component 可正常 render

