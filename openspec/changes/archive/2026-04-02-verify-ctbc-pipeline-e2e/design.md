## Context

CCAS 目前 CTBC 銀行的完整 pipeline 已實作五階段（ingest → decrypt → parse → classify → notify），且各階段均有單元測試、整合測試、E2E 測試覆蓋。本次驗證旨在系統性執行所有自動化測試，並搭配真實 pipeline 執行與手動 API/前端檢查，確認端到端流程無斷裂。

環境現況：
- Gmail 憑證（`data/credentials.json` + `data/token.json`）已存在
- `PDF_PASSWORD_CTBC` 已設定於 `.env`
- `API_TOKEN` 已設定
- SQLite DB（`data/ccas.db`）已存在且 migration 已套用

## Goals / Non-Goals

**Goals:**
- 執行全部自動化測試（unit / integration / e2e）確認 PASS
- 執行真實 CTBC pipeline 驗證 Gmail 拉取 → 解密 → 解析完整流程
- 驗證去重複機制正確運作（重複執行 skip，`--force` 覆寫）
- 驗證 API 端點回傳正確 CTBC 資料
- 驗證前端頁面正確渲染報表
- 修正驗證過程中發現的問題

**Non-Goals:**
- 不新增架構層級變更
- 不修改 API 合約或 DB schema
- 不新增其他銀行的 parser
- 不重構現有程式碼（除非修復 bug）

## Decisions

### 驗證分四層由內而外推進

1. **自動化測試層**：先跑 unit → integration → e2e，確認基礎正確
2. **真實 pipeline 層**：執行 `python -m ccas.pipeline --bank CTBC --year 2026 --month 3`，用 Python 腳本查詢 DB 驗證資料
3. **API 層**：啟動 FastAPI dev server，curl 驗證各端點
4. **前端層**：跑 vitest + 啟動前端 dev server 目視確認

**理由**：由內而外可在最早階段發現問題，避免浪費時間在後續層除錯。

### 去重複驗證策略

執行兩次 pipeline：
- 第一次正常執行，確認資料建立
- 第二次不帶 `--force`，確認 ingest 和 parse 階段 skipped > 0

**理由**：去重複是資料完整性的關鍵保障，需要明確驗證。

### 前端驗證以 vitest + API 回應檢查為主

前端未設定 Playwright E2E 測試，改用 vitest 單元測試 + curl API 端點驗證資料正確性。

**理由**：前端渲染依賴 API 資料，API 正確則前端渲染正確性由 vitest 保障。

## Risks / Trade-offs

| 風險 | 緩解 |
|------|------|
| Gmail OAuth token 過期 | Pipeline 會自動 refresh；若失敗需手動重新授權 |
| CTBC 帳單格式變更導致 parser 失敗 | 現有整合測試使用合成 PDF，不受影響；真實 pipeline 會在 parse 階段報錯 |
| 2026-03 月份無 CTBC 郵件 | 改用已存在的月份，或確認 DB 中已有資料 |
| SQLite 鎖定（pipeline + API 同時存取） | WAL mode 已啟用，支援並行讀取 |
