## Why

E2E walkthrough 問題 #8：FUBON 帳單無法經 pipeline 自動下載。目前 `FubonFetcher.fetch_pdf()` 在遇到 SPA 網域 `fbmbill.taipeifubon.com.tw` 時直接拋 `FetchError("SPA 流程尚未實作")`，整個 FUBON 的 ingest → decrypt → parse → classify 鏈路都走不通：使用者在前端永遠看不到 FUBON 的資料。

完整實作 SPA + API + OTP 自動化流程風險大（需要 playwright 環境、可能遇到 CAPTCHA、OTP 需要與 Telegram bot 串接），**不在本 change 範圍**。本 change 提供「人工橋接」方案：使用者從瀏覽器自行下載 PDF，放到約定目錄，pipeline 的 FUBON fetcher 以「讀取 manual-staging 資料夾」為 fallback。

此方案可讓 FUBON pipeline 立刻暢通，SPA 自動化則留給獨立 change 做 playwright 整合。

## What Changes

- **新增 `backend/src/ccas/ingestor/fetcher/banks/fubon_manual_staging.py`** 或在既有 `fubon.py` 內擴充邏輯：
  - 新增 `FUBON_MANUAL_STAGING_DIR` 設定（預設 `{DATA_DIR}/manual-staging/FUBON/`），於 `ccas.config.Settings` 加欄位。
  - `FubonFetcher.fetch_pdf()` 重構為：
    1. 先嘗試既有 HTML 解析路徑（若未來 SPA 被破解可以接回）。
    2. 若 HTML 路徑拋 `FetchError("SPA")`，fallback 到 manual staging 目錄。
    3. Manual staging 策略：從目錄列出 `*.pdf`，取檔名含 mail subject 中的帳單月份（或 `mtime` 最新的一份），**消費**該檔案（move 到 `ccas` 的正規 staging 結構）並回傳 path。
    4. 若目錄為空或沒有可對應的檔案 → 拋 `FetchError`，錯誤訊息明確指引使用者把 PDF 放到該目錄。
  - **幂等性**：manual staging 消費後檔案移除，下次 ingest 跑到同 mail 會拿不到 → 需檢查既有 bill 是否已存在以決定 skip（既有 ingestor 已有 idempotent hash 檢查，沿用即可）。
- **修改 `docs/user-guide.md`**：在「銀行支援現況」或 troubleshooting 新增「FUBON 手動下載步驟」說明：從登入頁面下載 PDF → 放到 `backend/data/manual-staging/FUBON/` → `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON`。
- **新增測試**：
  - `backend/tests/unit/ingestor/test_fubon_fetcher_manual_staging.py`：tmp_path fixture 模擬 staging 目錄的三種狀態（空、有檔、有檔但已消費）
  - `backend/tests/integration/ingestor/test_fubon_fetcher_e2e.py`：sandbox Gmail message + manual staging 檔案 → assert `fetch_pdf` 回傳 path 且檔案被移走

**非範圍**：
- 不實作 SPA playwright 自動化（留給 `add-fubon-spa-automation` 之類的後續 change）。
- 不改 `fetcher_registry` 或 `BankFetcher` 介面。
- 不動 `fubon-bootstrap`、`fubon-parser`、`fubon-fetcher-framework` 三個相關 spec。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `fubon-fetcher-impl`：將「SPA 尚未實作 → 永遠拋錯」的需求放寬為「若 SPA 路徑失敗，SHALL fallback 至 manual staging 目錄；僅當兩條路徑都無檔案時才拋 FetchError」。
- `user-guide`：新增 FUBON 手動下載操作步驟（小節或 troubleshooting 條目）。

## Impact

- **程式**：`backend/src/ccas/ingestor/fetcher/banks/fubon.py`、`backend/src/ccas/config.py`（新 Settings 欄位）
- **測試**：`backend/tests/unit/ingestor/test_fubon_fetcher_manual_staging.py`、`backend/tests/integration/ingestor/test_fubon_fetcher_e2e.py`
- **設定**：`.env.example` 新增 `FUBON_MANUAL_STAGING_DIR` 範例
- **相容性**：對既有 bank 路徑零影響；FUBON 使用者需額外一步（手動下載 PDF），但從完全不可用變為可用
- **風險**：使用者忘記放檔 → pipeline 回報 FetchError（符合 fail-fast 精神）
