## Why

執行富邦銀行完整下載流程（ingest → decrypt → parse → classify）後驗證 DB 資料，發現 parser 遺漏卡號與分期欄位、captcha OCR 無法不靠 LLM fallback 穩定達標、staging 路徑在 Docker/本機切換時斷裂。這些問題影響資料完整性與 pipeline 可靠性，需在下一輪迭代修正。

## What Changes

- **Parser 增強**：擷取 card_last4（從卡號分組標頭傳遞）、解析分期資訊（從 merchant 名稱提取 installment_current/total 並清理 merchant）
- **Captcha OCR 改進**：加入圖片前處理（灰階/二值化/降噪），擴充 fixture 集建立 eval harness，OCR-only 達 80% server-side 正確率
- **分類 seed 補充**：新增「保險」類 keyword（富邦產物保險等）
- **Staging 路徑修正**：staged_path 改為相對路徑或基於 STAGING_DIR 的動態解析，解決 Docker/本機不一致

## Capabilities

### New Capabilities
- `fubon-captcha-accuracy`: Captcha OCR 前處理 pipeline + eval harness，不靠 LLM fallback 達 80% server-side 正確率

### Modified Capabilities
- `fubon-parser`: 新增 card_last4 擷取（卡號分組標頭傳遞）+ 分期資訊解析（installment_current/total）
- `classification-seed`: 新增保險類 keyword mapping
- `docker-deployment`: staging 路徑策略統一（相對路徑或動態 resolve）

## Impact

- **Parser**: `backend/src/ccas/parser/banks/fubon_v1.py` — 新增 card header regex、installment regex、狀態傳遞邏輯
- **Captcha**: `backend/src/ccas/ingestor/fetcher/banks/fubon/captcha.py` — 前處理函式、confidence 門檻調整
- **Tests**: `backend/tests/fixtures/fubon/captcha_samples/` — 擴充至 ≥30 張、新增 eval script
- **Staging**: `backend/src/ccas/ingestor/staging.py` + `backend/src/ccas/decryptor/job.py` + `backend/src/ccas/parser/job.py` — 路徑解析邏輯
- **Seed**: classification seed data（`scripts/seed.py` 或 migration）
- **無 breaking change**：所有修改向後相容，新欄位填充為可選值
