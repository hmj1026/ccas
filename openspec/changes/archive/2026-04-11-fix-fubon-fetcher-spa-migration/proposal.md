# Proposal: fix-fubon-fetcher-spa-migration

## Why

現有 `FubonFetcher` 實作與富邦銀行**目前的帳單下載系統完全不符**，導致 pipeline 對 FUBON 所有歷史帳單（實測 201 封）`staged=0 skipped=0 failed=0`，完全無法取得任何資料。

### 三個根因（2026-04-11 實測確認）

1. **`can_fetch` 關鍵字匹配失敗**：
   - 現行 `fubon.py:23` 寫死 `_DOWNLOAD_LINK_TEXT = "下載帳單明細"`，以 BeautifulSoup `<a string="...">` 搜尋純文字錨點
   - 實際郵件 HTML 的下載錨點為：`<a href="..."><img alt="下載本期帳單(PDF)" /></a>`，`<a>` 內只有 `<img>`、無直接文字子節點
   - 201 封郵件全部 `can_fetch` 回傳 `False`，pipeline 無人認領

2. **網域白名單漏列**：
   - `_ALLOWED_DOMAINS` 只允許 `mybank/ecard/ebill/www/cf.taipeifubon.com.tw`
   - 實際下載服務網域為 **`fbmbill.taipeifubon.com.tw`**（不在白名單內）
   - 即使 `can_fetch` 修好，`_validate_url` 也會立即拋 `FetchError`

3. **下載流程架構過時**：
   - 舊實作假設：landing page 為傳統 server-rendered HTML + `<form>` + CAPTCHA `<img>`
   - 實測 landing page（`https://fbmbill.taipeifubon.com.tw/client/?code=<token>&bf=E`）為 **Vue SPA**（`<div id="app"></div>`），HTML 僅 1245 bytes
   - 認證流程由前端 JS 呼叫 axios API：`login(data) => req('post', 'doLogin', data)`
   - **無 CAPTCHA**（SPA JS bundle 全文搜尋 `captcha` 0 次命中）
   - 存在 OTP 驗證端點 `apiVerifyOtp`，可能觸發簡訊二階段驗證（完全阻擋自動化）
   - 直接 GET `/client/pdf/<token>` 回傳 SPA shell HTML，並非 PDF bytes

舊實作顯然是針對更早期（pre-SPA）的富邦帳單系統而設計，在富邦改版後已完全失效但未被測試捕捉到（因為 unit tests 用假 HTML fixture 仍可通過）。

## What Changes

本變更採取**誠實記錄現況 + 最小防呆修正**策略，**不嘗試完整重寫 SPA 流程**（因為 OTP 可能完全阻擋自動化，需另外設計）：

### 變更範圍

1. **修正 `can_fetch` 辨識邏輯**：改為偵測「任何指向 `fbmbill.taipeifubon.com.tw` 的 `<a>` 錨點」，不再依賴錨點內文字。這讓 pipeline 正確路由到 `_process_web_fetch` 分支，而不是靜默略過。

2. **補齊 `_ALLOWED_DOMAINS`**：加入 `fbmbill.taipeifubon.com.tw`，使 `_validate_url` 能通過真實下載網域。

3. **`fetch_pdf` 改為顯式 `NotImplementedError`**：改為拋出 `FetchError("FUBON", "富邦帳單系統已遷移為 SPA + OTP 流程，自動下載尚未實作；請改以手動方式取得 PDF 後放入 staging 目錄")`。這讓使用者看到明確錯誤訊息而非神秘失敗，並在 JSON summary 中可見。

4. **更新 unit test fixtures**：新增「img-wrapped 錨點」真實 HTML 範例，避免未來回歸。刪除過時的 CAPTCHA OCR 測試假設（改為測 NotImplementedError 路徑）。

5. **更新 OpenSpec `fubon-fetcher-impl` 規格**：反映 SPA 時代的新行為，`CAPTCHA OCR 工具` 相關 requirement 被標記為 `REMOVED`（OCR 基礎設施仍保留給未來他行使用，但 FUBON 不再依賴它）。

### 非變更範圍

- **不改動** `solve_captcha()` 工具或其他非 FUBON 的 web fetch 基礎設施
- **不改動** FUBON PDF 解析器（`FubonV1Parser`）— 拿到 PDF bytes 後的流程沒變
- **不改動** Gmail ingestion 或 pipeline 排程邏輯
- **不嘗試** reverse-engineer SPA API bundle；這需要獨立的後續變更（並需使用者確認是否接受 OTP 手動介入）

## Impact

### Affected specs
- `fubon-fetcher-impl` — `can_fetch` 行為重寫；`fetch_pdf` 行為改為明確回報未實作；`CAPTCHA OCR 工具` requirement 移除對 FUBON 的關聯（保留純工具 requirement）

### Affected code
- `backend/src/ccas/ingestor/fetcher/banks/fubon.py` — `can_fetch`、`_ALLOWED_DOMAINS`、`fetch_pdf` 三處
- `backend/tests/unit/ingestor/fetcher/test_fubon.py` — 更新 fixture 與測試案例

### Affected runtime behaviour
- **Before**: FUBON pipeline run 靜默 0 結果，使用者無任何線索
- **After**: FUBON pipeline run 對每封含下載連結的郵件回報 `failed` 且帶明確錯誤訊息「富邦帳單系統已遷移為 SPA + OTP 流程，自動下載尚未實作」— 使用者可立即決定手動處理或等待後續自動化實作

### Migration / backfill
- 既有 FUBON DB 資料：無（一開始就 staged=0）— 無 migration 需求
- 使用者若要補齊歷史 FUBON 帳單，需手動從網銀下載 PDF 並透過後續變更提供的匯入工具（另外設計）放入 staging

### Follow-up work（不屬本變更）
- 反向工程 FUBON SPA bundle、設計 `POST doLogin` + OTP handling 流程 → 另開變更 `add-fubon-spa-api-fetcher`
- 提供「手動 PDF 放入 staging 目錄」匯入工具 → 另開變更 `add-manual-staging-importer`
