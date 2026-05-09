## Why

CTBC 是目前唯一已實作的銀行解析器，需要端到端驗證完整 pipeline 流程（Gmail 拉取 → 去重複/略過 → 解密 → 解析 → API 回應 → 前端報表顯示）以確認各環節正確串接。目前缺乏一個系統性的驗證流程，將各階段的自動化測試與真實 pipeline 執行、API 端點驗證、前端渲染一併確認。

## What Changes

- 執行現有單元測試、整合測試、E2E 測試套件，確認各元件獨立正確性
- 執行真實 CTBC pipeline（Gmail → decrypt → parse），驗證資料正確寫入 DB
- 驗證去重複機制（重複執行時正確 skip，`--force` 時正確覆寫）
- 驗證 API 端點回傳正確 CTBC 帳單/交易資料
- 驗證前端頁面可正確渲染 CTBC 報表（Overview、Bills、Transactions、Analytics）
- 若發現問題，修正相關程式碼

## Capabilities

### New Capabilities

（無新增 capability，本次為驗證現有功能）

### Modified Capabilities

- `e2e-pipeline-tests`: 若驗證過程發現測試覆蓋不足，補充相關測試案例
- `ctbc-parser`: 若解析結果與預期不符，修正 parser 邏輯

## Impact

- 涉及模組：ingestor、decryptor、parser、classifier、API routers、frontend pages
- 不影響 API 合約或 DB schema
- 可能產出：測試補充、bug fix patch
