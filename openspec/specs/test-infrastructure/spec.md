# test-infrastructure Specification

## Purpose
TBD - created by archiving change foundation-setup. Update Purpose after archive.
## Requirements
### Requirement: 後端 pytest 設定
系統 SHALL 透過 `pyproject.toml` 設定 pytest，並將測試目錄設為 `backend/tests/unit/` 與 `backend/tests/integration/`。coverage 報告 SHALL 針對 `ccas` package 啟用，且 unit-only 量測的最低門檻 SHALL 為 **80%**（`fail_under = 80`）。

unit 覆蓋率量測的 omit list SHALL 包含下列模組（這些模組皆由 integration tests 完整覆蓋，不適合 unit mock）：
- `src/ccas/*/app.py`
- `src/ccas/*/__main__.py`
- `src/ccas/scheduler/reminders.py`
- `src/ccas/api/routers/analytics.py`
- `src/ccas/api/routers/overview.py`
- `src/ccas/api/routers/pipeline.py`
- `src/ccas/api/routers/transactions.py`
- `src/ccas/api/routers/settings.py`
- `src/ccas/api/routers/setup/admin.py`
- `src/ccas/api/routers/setup/banks.py`
- `src/ccas/api/routers/setup/gmail.py`
- `src/ccas/api/routers/setup/login_credentials.py`
- `src/ccas/api/routers/setup/secrets.py`
- `src/ccas/api/routers/staged_attachments.py`
- `src/ccas/api/routers/transactions_edit.py`

#### Scenario: pytest 可發現並執行測試
- **WHEN** 在 `backend/` 目錄執行 `uv run pytest`
- **THEN** pytest 會找到 `tests/unit/` 與 `tests/integration/` 下的測試並執行

#### Scenario: 產生 coverage 報告
- **WHEN** 執行 `uv run pytest --cov=ccas --cov-report=term-missing`
- **THEN** 會顯示涵蓋 `ccas` 所有模組逐行資訊的 coverage 報告

#### Scenario: unit-only 覆蓋率閘門通過
- **WHEN** 執行 `pytest tests/unit/ --cov --cov-fail-under=80`
- **THEN** 所有非 omit 模組的 unit 覆蓋率合計 ≥ 80%，指令 exit code 為 0

#### Scenario: 覆蓋率不足時 CI 失敗
- **WHEN** unit 覆蓋率低於 80%
- **THEN** `pytest` 以非零 exit code 結束，CI job 標記為 FAIL

### Requirement: 核心子系統模組 unit 覆蓋率 ≥ 80%
下列核心子系統的 `src/ccas/` 模組——pipeline、classifier、decryptor、ingestor、parser、scheduler、storage、tools、bot——其每個非 omit 模組 SHALL 個別達到 ≥ 80% 的 unit statement 覆蓋率。

> 範圍註記：`api/` 層（routers 與 `deps.py` / `ratelimit.py`）不在本要求範圍內。該層的 router 由 CI 獨立的 router-coverage job（`--cov=src/ccas/api/routers --cov-fail-under=50`）與 `tests/integration/` 管轄；純 integration-tested 的 router 另列入上方 omit list。整體 unit 閘門（`fail_under = 80`）仍涵蓋所有未 omit 模組的合計覆蓋率。

#### Scenario: pipeline/worker 覆蓋率達標
- **WHEN** 執行 `pytest tests/unit/pipeline/ --cov=ccas.pipeline.worker`
- **THEN** `ccas.pipeline.worker` 的覆蓋率 ≥ 80%

#### Scenario: tools/categories 有 unit tests
- **WHEN** 執行 `pytest tests/unit/tools/test_categories.py`
- **THEN** 測試通過，`tools/categories.py` 覆蓋率 ≥ 80%

#### Scenario: tools/reclassify 有 unit tests
- **WHEN** 執行 `pytest tests/unit/tools/test_reclassify.py`
- **THEN** 測試通過，`tools/reclassify.py` 覆蓋率 ≥ 80%

#### Scenario: classifier/user_rules 覆蓋率達標
- **WHEN** 執行 `pytest tests/unit/classifier/ --cov=ccas.classifier.user_rules`
- **THEN** `ccas.classifier.user_rules` 的覆蓋率 ≥ 80%

#### Scenario: ingestor/job 覆蓋率達標
- **WHEN** 執行 `pytest tests/unit/ingestor/ --cov=ccas.ingestor.job`
- **THEN** `ccas.ingestor.job` 的覆蓋率 ≥ 80%

### Requirement: omit list 模組由 integration tests 補足覆蓋
所有進入 omit list 的模組 SHALL 在 `tests/integration/` 中有對應的測試檔，且整合測試 SHALL 覆蓋主要的 happy path 與 error path。

#### Scenario: setup/banks router 整合測試存在
- **WHEN** 執行 `pytest tests/integration/test_setup_banks_router.py`
- **THEN** 測試通過，覆蓋 banks router 的主要路徑

#### Scenario: transactions_edit router 整合測試存在
- **WHEN** 執行 `pytest tests/integration/test_transactions_edit.py`
- **THEN** 測試通過，覆蓋 transactions_edit router 的主要路徑

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

系統 SHALL 在 `vite.config.ts` 的 `test.coverage` 啟用 v8 provider 的覆蓋率量測，`include` SHALL 為 `src/**/*.{ts,tsx}` 並排除測試檔與 `test-*` 輔助檔。覆蓋率門檻 SHALL 為四項指標皆 ≥ **80**：`lines: 80`、`functions: 80`、`statements: 80`、`branches: 80`。

#### Scenario: vitest 可發現並執行測試
- **WHEN** 在 `frontend/` 目錄執行 `pnpm test`
- **THEN** vitest 會找到並執行所有符合命名慣例的測試檔

#### Scenario: 覆蓋率達標時通過
- **WHEN** 在 `frontend/` 目錄執行 `pnpm test --coverage`
- **THEN** lines / functions / statements / branches 四項覆蓋率皆 ≥ 80，指令 exit code 為 0

#### Scenario: 覆蓋率不足時 CI 失敗
- **WHEN** 四項覆蓋率指標中任一項低於 80
- **THEN** `vitest` 以非零 exit code 結束，CI `frontend-lint-test` job 標記為 FAIL

### Requirement: 提供前端 smoke test
系統 SHALL 包含一個 smoke test，驗證 React App component 可正常 render。

#### Scenario: App 元件 render 測試通過
- **WHEN** 執行 `pnpm test`
- **THEN** smoke test 會通過，證明 App component 可正常 render

### Requirement: Cross-platform CJK font fixture for parser integration tests
Parser integration tests SHALL use a shared `cjk_font_path` fixture that resolves CJK font paths across Linux and macOS, skipping tests when no font is available.

#### Scenario: Linux Docker environment with wqy-zenhei
- **WHEN** `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc` exists
- **THEN** the fixture SHALL return that path and all parser integration tests SHALL run

#### Scenario: macOS with system CJK font
- **WHEN** Linux font is absent but `/System/Library/Fonts/STHeiti Medium.ttc` exists
- **THEN** the fixture SHALL return the macOS path and all parser integration tests SHALL run

#### Scenario: No CJK font available
- **WHEN** no candidate CJK font path exists
- **THEN** the fixture SHALL call `pytest.skip()` and tests SHALL be marked as skipped (not failed)

### Requirement: 前端覆蓋率閘門於 CI 與 pre-push 雙重強制
前端覆蓋率閘門 SHALL 同時於 CI 與本地 pre-push 強制，且兩者 SHALL 等價（皆執行帶覆蓋率的 vitest）。`scripts/pre-push.sh` 的前端步驟 SHALL 以 `--coverage` 執行 vitest，使覆蓋率不足在本地推送前即被攔截。

#### Scenario: CI 以覆蓋率閘門執行前端測試
- **WHEN** CI `frontend-lint-test` job 執行 `pnpm run test --coverage`
- **THEN** 任一覆蓋率指標 < 80 時 job 以非零 exit code 失敗

#### Scenario: pre-push 本地強制前端覆蓋率
- **WHEN** 開發者執行 `scripts/pre-push.sh`（且未以 `RUN_FRONTEND=0` 略過前端）
- **THEN** 前端步驟以 `--coverage` 執行 vitest，覆蓋率不足時 pre-push 失敗並阻止 push

#### Scenario: pre-push 與 CI 等價
- **WHEN** 比對 `scripts/pre-push.sh` 前端步驟與 CI `frontend-lint-test` 的測試指令
- **THEN** 兩者皆執行帶 `--coverage` 的 vitest，套用相同的 `vite.config.ts` 門檻（SSOT）

