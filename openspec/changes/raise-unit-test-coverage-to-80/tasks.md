## 1. 設定調整（先行，確立新基線）

- [ ] 1.1 在 `backend/pyproject.toml` 的 `[tool.coverage.run] omit` 中新增 6 個 setup/edit router：`setup/banks.py`、`setup/gmail.py`、`setup/login_credentials.py`、`setup/secrets.py`、`staged_attachments.py`、`transactions_edit.py`
- [ ] 1.2 執行 `pytest tests/unit/ --cov=ccas --cov-report=term-missing` 確認新基線覆蓋率（排除 6 個 router 後預估 ~73–74%）
- [ ] 1.3 驗證 `tests/integration/test_setup_banks_router.py`、`test_staged_attachments.py`、`test_transactions_edit.py`、`test_setup_gmail.py`、`test_setup_login_credentials_router.py`、`test_setup_secrets_router.py` 全部通過（確保 omit 的模組已有整合覆蓋）

## 2. tools 模組補強（0% → ≥80%）

- [ ] 2.1 新增 `tests/unit/tools/test_categories.py`，覆蓋 `categories.py` 的分類讀取、seed 邏輯、錯誤路徑（目標 ≥80%）
- [ ] 2.2 新增 `tests/unit/tools/test_reclassify.py`，覆蓋 `reclassify.py` 的重分類流程（目標 ≥80%）
- [ ] 2.3 補強 `tests/unit/tools/test_cleanup_gmail_state.py`，覆蓋未測函式（46% → ≥80%）
- [ ] 2.4 補強 `tests/unit/tools/test_seed_bank_settings.py`，覆蓋 seed 各銀行設定路徑（56% → ≥80%）

## 3. pipeline 模組補強（32–41%）

- [ ] 3.1 補強 `tests/unit/pipeline/test_worker.py`，覆蓋 worker 主流程、錯誤處理、狀態轉換（41% → ≥80%）
- [ ] 3.2 新增 `tests/unit/pipeline/test_progress.py`（或補強既有），覆蓋 `progress.py` 的進度回報、callback 路徑（32% → ≥80%）

## 4. bot 模組補強（35%）

- [ ] 4.1 補強 `tests/unit/bot/test_queries.py`，覆蓋 `bot/queries.py` 的各 DB query helper（35% → ≥80%）

## 5. scheduler 模組補強（45%）

- [ ] 5.1 補強 `tests/unit/scheduler/test_jobs.py`，覆蓋 `scheduler/jobs.py` 的排程觸發、錯誤路徑（45% → ≥80%）

## 6. classifier 模組補強（47–77%）

- [ ] 6.1 補強 `tests/unit/classifier/test_engine.py` 或新增，覆蓋 `classifier/staging.py` 的暫存讀寫（47% → ≥80%）
- [ ] 6.2 補強 `tests/unit/classifier/test_rules.py`，覆蓋規則匹配的邊界條件（77% → ≥80%）
- [ ] 6.3 新增或補強 `tests/unit/classifier/test_user_rules.py`（若未存在），覆蓋用戶規則載入、解析、評估（47% → ≥80%）

## 7. decryptor 模組補強（47%）

- [ ] 7.1 補強 `tests/unit/decryptor/test_job.py`，覆蓋 `decryptor/job.py` 的協調邏輯、多密碼回退、錯誤路徑（47% → ≥80%）

## 8. ingestor 模組補強（47–54%）

- [ ] 8.1 新增 `tests/unit/ingestor/test_credentials.py`，覆蓋 `ingestor/credentials.py`（47% → ≥80%）
- [ ] 8.2 補強 `tests/unit/ingestor/test_job.py`（或分拆），覆蓋 `ingestor/job.py` 的主流程、過濾、重試（54% → ≥80%）

## 9. parser 模組補強（47–75%）

- [ ] 9.1 補強 `tests/unit/parser/` 中對 `parser/staging.py` 的測試，覆蓋 staging 讀寫路徑（47% → ≥80%）
- [ ] 9.2 補強 `tests/unit/parser/test_sinopac_v1.py`，覆蓋 sinopac_v1 未測分支（68% → ≥80%）
- [ ] 9.3 補強 `tests/unit/parser/test_taishin_v1.py`，覆蓋 taishin_v1 未測分支（75% → ≥80%）
- [ ] 9.4 補強 `tests/unit/parser/` 對 `parser/job.py` 的測試，覆蓋 job 協調邏輯（62% → ≥80%）

## 10. storage 模組補強（68%）

- [ ] 10.1 補強 `tests/unit/storage/test_database.py`，覆蓋 `storage/database.py` 的連線建立、錯誤處理（68% → ≥80%）

## 11. 閘門升級與驗證

- [ ] 11.1 確認 `pytest tests/unit/ --cov=ccas --cov-report=term-missing` 整體覆蓋率 ≥ 80%
- [ ] 11.2 將 `backend/pyproject.toml` 的 `[tool.coverage.report] fail_under` 由 70 改為 80
- [ ] 11.3 更新 `.github/workflows/ci.yaml`（若有硬編碼 `--cov-fail-under=70`）改為 80
- [ ] 11.4 更新 `scripts/pre-push.sh`（若有硬編碼 `--cov-fail-under=70`）改為 80
- [ ] 11.5 更新 `pyproject.toml` 中的 omit list 說明註解，記錄 6 個新增 router 的理由
- [ ] 11.6 執行完整套件 `pytest tests/unit/ tests/integration/ -q` 確認無回歸
