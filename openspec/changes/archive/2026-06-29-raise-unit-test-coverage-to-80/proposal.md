## Why

CCAS 的單元測試覆蓋率目前為 71.4%，高於 CI 閘門 70% 但低於既定目標 80%；有 8 個模組的 unit 覆蓋率為 0%、10 個模組低於 50%，這些模組缺乏回歸安全網，在重構或功能迭代時容易引入隱性錯誤而無法被及早攔截。

## What Changes

- 將 `pyproject.toml` 的 `fail_under` 從 70 提升至 80
- 為 `tools/categories.py`、`tools/reclassify.py` 新增 unit tests（目前 0%，無任何測試）
- 補強 `pipeline/progress.py`（32%）、`pipeline/worker.py`（41%）、`bot/queries.py`（35%）、`scheduler/jobs.py`（45%）、`classifier/staging.py`（47%）、`classifier/user_rules.py`（47%）、`decryptor/job.py`（47%）、`ingestor/credentials.py`（47%）、`ingestor/job.py`（54%）、`parser/staging.py`（47%）的 unit tests
- 補強 `parser/job.py`（62%）、`parser/banks/sinopac_v1.py`（68%）、`parser/banks/taishin_v1.py`（75%）、`storage/database.py`（68%）、`classifier/rules.py`（77%）、`tools/seed_bank_settings.py`（56%）的 unit tests
- 為 0% 的 setup routers（`setup/admin.py`、`setup/banks.py`、`setup/gmail.py`、`setup/login_credentials.py`、`setup/secrets.py`、`staged_attachments.py`、`transactions_edit.py`，共 7 個）制定策略：這些 router 已有完整 integration tests，加入 `pyproject.toml` omit list 排除於 unit 測量，與現行 omit pattern 一致

## Capabilities

### New Capabilities

（無）— 本次為品質補強，不引入新行為。

### Modified Capabilities

- `test-infrastructure`: 覆蓋率閘門由 70% 提升至 80%；omit list 新增 6 個 setup/transaction-edit router（已有 integration tests 覆蓋，符合既有「router 歸 integration」慣例）

## Impact

- `backend/pyproject.toml`：`fail_under = 80`、omit list 新增 6 個 router
- `backend/tests/unit/` 新增 tests（不修改既有測試）：tools/、pipeline/、bot/、scheduler/、classifier/、decryptor/、ingestor/、parser/、storage/ 各子目錄
- CI `backend-test` job：閘門提升後若現有測試不足會 fail（此為預期行為）
- 不影響 API 端點、資料庫 schema、前端、Docker 設定
