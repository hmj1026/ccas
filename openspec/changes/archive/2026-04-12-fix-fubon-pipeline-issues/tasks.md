## 1. Parser: card_last4 + 分期資訊

- [x] 1.1 新增 card header regex（偵測「末４碼NNNN」pattern），在 `_extract_transactions_text()` 中維護 `current_card_last4` 狀態
- [x] 1.2 新增 installment regex（偵測 `(NN/MM期)` pattern），從 merchant 提取 installment_current/total 並清理 merchant 名稱
- [x] 1.3 為 card_last4 傳遞撰寫 unit test（含多卡號切換情境）
- [x] 1.4 為 installment 解析撰寫 unit test（含無分期、有分期、多分期情境）
- [x] 1.5 以現有 fixture PDF 驗證 integration test：確認 7 筆交易中 card_last4 = "5273"、保險交易 installment = 1/6

## 2. Classification seed: 新增保險類

- [x] 2.1 在 `config/categories.yaml` 新增「保險」category 及 keywords（富邦產物保險、國泰產險、新光產險等）
- [x] 2.2 執行 `uv run python -m ccas.tools.categories --apply` 驗證 seed 結果
- [x] 2.3 重跑 classify pipeline 驗證「富邦產物保險」歸類為「保險」

## 3. Staging 路徑: 改為相對路徑

- [x] 3.1 修改 `staging.py` 的 `build_staged_path()` 回傳相對路徑（相對於 STAGING_DIR）
- [x] 3.2 修改 `ingestor/job.py` 的 `create_staged_record()` 儲存相對路徑
- [x] 3.3 修改 `decryptor/job.py` 與 `parser/job.py` 讀取時以 `settings.staging_dir / staged_path` 組合
- [x] 3.4 撰寫 migration script `scripts/migrate_staging_paths.py`，將既有絕對路徑轉為相對路徑（idempotent）
- [x] 3.5 為路徑組合邏輯撰寫 unit test（Docker 路徑 + 本機路徑情境）
- [x] 3.6 執行 migration script 並驗證既有 record 路徑正確

## 4. Captcha OCR: 前處理 + eval harness

- [x] 4.1 在 `captcha.py` 新增 `_preprocess(jpeg_bytes) -> bytes` 函式（Pillow: 灰階 → 對比增強 → Otsu 二值化 → median filter）
- [x] 4.2 修改 `solve()` 在呼叫 ddddocr 前先執行 `_preprocess()`
- [x] 4.3 為 `_preprocess()` 撰寫 unit test（正常圖片、損壞圖片 fallback）
- [x] 4.4 建立 `scripts/eval_captcha.py` eval harness，統計 accept rate + accuracy，accuracy < 80% 時 exit code 1
- [x] 4.5 收集真實 captcha 樣本至 `tests/fixtures/fubon/captcha_samples/`，45 張人工校驗完成（100% accuracy）
- [x] 4.6 在 `config.py` 新增 `FUBON_CAPTCHA_ARCHIVE_DIR` 設定，`flow.py` 中成功驗證後儲存 captcha JPEG
- [x] 4.7 以 eval harness 驗證前處理後 accuracy ≥ 80%（10 張 fixture: 90% accept, 100% accuracy — PASS）

## 5. 驗證與收尾

- [x] 5.1 跑完整 Fubon pipeline（ingest → decrypt → parse → classify）驗證 DB 資料正確（8 bills parsed, 42 txns classified）
- [x] 5.2 確認所有 unit/integration test 通過（933 passed）
- [x] 5.3 確認 ruff lint + pyright type check 通過（0 errors）
