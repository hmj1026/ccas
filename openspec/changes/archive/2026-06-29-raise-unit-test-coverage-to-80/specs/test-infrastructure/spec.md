## MODIFIED Requirements

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

## ADDED Requirements

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
