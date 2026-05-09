## 1. 修正 mock path

- [x] 1.1 讀取 `ccas.decryptor.job` 確認 import 名稱與 `decrypt_pdf_multi` 的呼叫簽名 / 回傳型別
- [x] 1.2 更新 `tests/e2e/test_pipeline_happy_path.py` 的 mock target 和 return value
- [x] 1.3 更新 `tests/e2e/test_pipeline_error_path.py` 的 mock target 和 side_effect

## 2. 驗證

- [x] 2.1 `uv run pytest tests/e2e/ -q` 7 tests PASS
