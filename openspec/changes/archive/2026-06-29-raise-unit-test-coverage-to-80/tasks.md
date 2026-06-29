## 1. 設定調整（先行，確立新基線）

- [x] 1.1 在 `backend/pyproject.toml` 的 `[tool.coverage.run] omit` 中新增 7 個 setup/edit router：`setup/admin.py`、`setup/banks.py`、`setup/gmail.py`、`setup/login_credentials.py`、`setup/secrets.py`、`staged_attachments.py`、`transactions_edit.py`（admin 與其餘 setup router 同屬 integration-tested，依 design D1 一併排除）
- [x] 1.2 執行 `pytest tests/unit/ --cov=ccas --cov-report=term-missing` 確認新基線覆蓋率（排除 6 個 router 後實測 76.61%）
- [x] 1.3 驗證 `tests/integration/test_setup_banks_router.py`、`test_staged_attachments.py`、`test_transactions_edit.py`、`test_setup_gmail.py`、`test_setup_login_credentials_router.py`、`test_setup_secrets_router.py` 全部通過（93 passed，確保 omit 的模組已有整合覆蓋）

## 2. tools 模組補強（0% → ≥80%）

- [x] 2.1 新增 `tests/unit/tools/test_categories.py`，覆蓋 `categories.py` 的分類讀取、seed 邏輯、錯誤路徑（實測 99%）
- [x] 2.2 新增 `tests/unit/tools/test_reclassify.py`，覆蓋 `reclassify.py` 的重分類流程（實測 94%）
- [x] 2.3 補強 `tests/unit/tools/test_cleanup_gmail_state.py`，覆蓋未測函式（46% → 97%）
- [x] 2.4 補強 `tests/unit/tools/test_seed_bank_settings.py`，覆蓋 seed 各銀行設定路徑（56% → 99%）

## 3. pipeline 模組補強（32–41%）

- [x] 3.1 補強 `tests/unit/pipeline/test_worker.py`，覆蓋 worker 主流程、錯誤處理、狀態轉換（41% → 98%）
- [x] 3.2 新增 `tests/unit/pipeline/test_progress.py`，覆蓋 `progress.py` 的進度回報、callback 路徑（32% → 100%）

## 4. bot 模組補強（35%）

- [x] 4.1 新增 `tests/unit/bot/test_queries.py`，覆蓋 `bot/queries.py` 的各 DB query helper（35% → 100%）

## 5. scheduler 模組補強（45%）

- [x] 5.1 補強 `tests/unit/scheduler/test_jobs.py`，覆蓋 `scheduler/jobs.py` 的排程觸發、錯誤路徑（45% → 100%）

## 6. classifier 模組補強（47–77%）

- [x] 6.1 新增 `tests/unit/classifier/test_staging.py`，覆蓋 `classifier/staging.py` 的暫存讀寫（47% → 100%）
- [x] 6.2 補強 `tests/unit/classifier/test_rules.py`，覆蓋規則匹配的邊界條件（77% → 100%）
- [x] 6.3 新增 `tests/unit/classifier/test_user_rules.py`，覆蓋用戶規則載入、解析、評估（47% → 100%）

## 7. decryptor 模組補強（47%）

- [x] 7.1 新增 `tests/unit/decryptor/test_job.py`，覆蓋 `decryptor/job.py` 的協調邏輯、多密碼回退、錯誤路徑（47% → 98%）

## 8. ingestor 模組補強（47–54%）

- [x] 8.1 新增 `tests/unit/ingestor/test_credentials.py`，覆蓋 `ingestor/credentials.py`（47% → 100%）
- [x] 8.2 新增 `tests/unit/ingestor/test_job.py`，覆蓋 `ingestor/job.py` 的主流程、過濾、重試（54% → 81%）

## 9. parser 模組補強（47–75%）

- [x] 9.1 新增 `tests/unit/parser/test_staging.py`，覆蓋 `parser/staging.py` staging 讀寫路徑（47% → 100%）
- [x] 9.2 補強 `tests/unit/parser/test_sinopac_v1.py`，覆蓋 sinopac_v1 未測分支（68% → 100%）
- [x] 9.3 補強 `tests/unit/parser/test_taishin_v1.py`，覆蓋 taishin_v1 未測分支（75% → 100%）
- [x] 9.4 新增 `tests/unit/parser/test_job.py`，覆蓋 `parser/job.py` job 協調邏輯（62% → 84%）

## 10. storage 模組補強（68%）

- [x] 10.1 補強 `tests/unit/storage/test_database.py`，覆蓋 `storage/database.py` 的連線建立、錯誤處理（68% → 100%）

## 11. 閘門升級與驗證

- [x] 11.1 確認 `pytest tests/unit/ --cov=ccas --cov-report=term-missing` 整體覆蓋率 ≥ 80%（實測 89.53%）
- [x] 11.2 將 `backend/pyproject.toml` 的 `[tool.coverage.report] fail_under` 由 70 改為 80
- [x] 11.3 更新 `.github/workflows/ci.yaml` 的 `--cov-fail-under=70` 改為 80
- [x] 11.4 更新 `scripts/pre-push.sh` 的 `--cov-fail-under=70` 改為 80
- [x] 11.5 更新 `pyproject.toml` 中的 omit list 說明註解，記錄 6 個新增 router 的理由
- [x] 11.6 執行完整套件 `pytest tests/unit/ tests/integration/ -q` 確認無回歸（2009 passed, 1 deselected, 0 failed）
