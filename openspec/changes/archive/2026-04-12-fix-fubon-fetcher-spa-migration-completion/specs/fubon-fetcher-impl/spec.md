## MODIFIED Requirements

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 嘗試從郵件 HTML 下載 PDF 帳單。當目標下載系統（`fbmbill.taipeifubon.com.tw` 等）為 SPA + API + 可能 OTP 的架構且自動化流程尚未實作時，SHALL fallback 至 **manual staging 目錄** 搜尋由使用者手動放入的 PDF 檔案。僅當 HTML 路徑與 manual staging 路徑**兩者皆無可用檔案**時，SHALL 拋出 `FetchError`，錯誤訊息 MUST 明確指引使用者將 PDF 放入 manual staging 目錄。

#### Scenario: SPA 路徑失敗時 fallback 至 manual staging（檔案存在）

- **GIVEN** `fetch_pdf()` 被呼叫且 HTML 解析路徑因 SPA 網域失敗
- **AND** `Settings.fubon_manual_staging_dir` 目錄內存在對應月份的 `.pdf` 檔案
- **WHEN** fetcher 執行 fallback
- **THEN** SHALL 從 manual staging move 該 PDF 至 `Settings.staging_dir/FUBON/`，回傳該路徑，不拋例外

#### Scenario: Manual staging 目錄為空時拋出明確 FetchError

- **GIVEN** HTML 路徑失敗且 manual staging 目錄為空
- **WHEN** `fetch_pdf()` 被呼叫
- **THEN** SHALL 拋出 `FetchError`，`bank_code="FUBON"`，訊息 MUST 包含 manual staging 目錄絕對路徑與建議動作「從富邦網銀下載 PDF 並放入該目錄」

#### Scenario: 檔名含帳單月份時精確配對

- **GIVEN** manual staging 目錄含 `fubon-2026-03.pdf` 與 `fubon-2026-04.pdf`
- **AND** 觸發 fetch 的 Gmail message 推導出帳單月份為 `2026-03`
- **WHEN** fetcher 選檔
- **THEN** SHALL 選到 `fubon-2026-03.pdf`

#### Scenario: 檔名不含月份時採 mtime 最新

- **GIVEN** manual staging 目錄內只有 `statement.pdf` 單一檔案且檔名不含月份
- **WHEN** fetcher 選檔
- **THEN** SHALL 選到該檔案

#### Scenario: 多檔無法區分月份時拋 FetchError

- **GIVEN** manual staging 內有 2 個無月份檔名且 mtime 相近
- **WHEN** fetcher 選檔
- **THEN** SHALL 拋出 `FetchError`，訊息包含「manual staging 目錄有多個無法對應的檔案」

#### Scenario: URL 提取失敗（HTML 無下載連結）仍走 fallback

- **GIVEN** HTML body 中找不到任何指向 `_ALLOWED_DOMAINS` 的連結
- **AND** manual staging 目錄有可用檔案
- **WHEN** `fetch_pdf()` 被呼叫
- **THEN** SHALL 進入 manual staging 路徑並成功回傳，不拋 `FetchError`
