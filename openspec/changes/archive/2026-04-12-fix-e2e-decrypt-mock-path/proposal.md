## Why

2 個 e2e 測試（`test_pipeline_happy_path.py` 和 `test_pipeline_error_path.py`）因 mock path `ccas.decryptor.job.decrypt_pdf` 過時而 FAIL。實際函式已重構為 `decrypt_pdf_multi`（支援多密碼 fallback），但 e2e test 的 mock 未同步更新。

## What Changes

- 更新 `tests/e2e/test_pipeline_happy_path.py`：mock path `decrypt_pdf` → `decrypt_pdf_multi`
- 更新 `tests/e2e/test_pipeline_error_path.py`：同上

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `e2e-pipeline-tests`: mock target 需與 `decryptor.job` 實際 import 一致

## Impact

- 僅影響 2 個 e2e 測試檔
- 無生產程式碼變更
