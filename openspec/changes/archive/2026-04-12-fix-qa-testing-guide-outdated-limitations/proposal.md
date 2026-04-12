## Why

`docs/qa-testing-guide.md` 的「已知限制」段落嚴重過時，會誤導 QA 人員認為系統僅支援 CTBC 一家銀行、且 bot 無自動化測試。此外測試數量從文件記載的 495 增長至 1032+，數據不符。`docs/e2e-user-guide-walkthrough.md` 的問題追蹤表也有未歸檔項目。

## What Changes

- 更新 `docs/qa-testing-guide.md` §已知限制 #1：「僅支援 CTBC」→ 列出 7 家已支援銀行（CTBC / SINOPAC / ESUN / UBOT / CATHAY / TAISHIN / FUBON）
- 更新 `docs/qa-testing-guide.md` §已知限制 #4：「Bot handlers 無自動化測試」→ 移除（已有 unit + integration tests）
- 更新 `docs/qa-testing-guide.md` §自動化測試：「495 tests」→ 更新為實際數字
- 更新 `docs/e2e-user-guide-walkthrough.md` 問題追蹤表 #10：`applied` → `archived`

## Capabilities

### New Capabilities

（無新增功能）

### Modified Capabilities

- `user-guide`: QA testing guide 為 user-guide 的延伸文件，限制段落的更正確保文件與實際系統能力一致

## Impact

- 僅影響 `docs/` 下 2 個 markdown 文件
- 無程式碼、API、依賴或系統變更
