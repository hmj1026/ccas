# Spec Delta: fubon-fetcher-impl

## MODIFIED Requirements

### Requirement: can_fetch 辨識富邦下載連結

`FubonFetcher.can_fetch()` SHALL 從郵件 HTML body 中偵測任何指向 FUBON 官方帳單下載網域（`_ALLOWED_DOMAINS`）的 `<a>` 錨點，以支援富邦帳單系統遷移為 SPA 後以圖片按鈕取代純文字連結的郵件格式。辨識邏輯不再依賴錨點內的文字內容。

#### Scenario: 錨點內為 img 按鈕（SPA 時代新格式）
- **WHEN** HTML body 包含 `<a href="https://fbmbill.taipeifubon.com.tw/..."><img alt="下載本期帳單(PDF)" /></a>`
- **THEN** `can_fetch()` SHALL 回傳 `True`

#### Scenario: 錨點內為純文字（舊格式，保留相容）
- **WHEN** HTML body 包含 `<a href="https://mybank.taipeifubon.com.tw/...">下載帳單明細</a>`
- **THEN** `can_fetch()` SHALL 回傳 `True`

#### Scenario: 錨點指向非 FUBON 官方網域
- **WHEN** HTML body 包含的所有 `<a href="...">` 均指向 `_ALLOWED_DOMAINS` 以外的網域
- **THEN** `can_fetch()` SHALL 回傳 `False`

#### Scenario: 空或無效 HTML 不導致例外
- **WHEN** HTML body 為 None、空字串或無效 HTML
- **THEN** `can_fetch()` SHALL 回傳 `False`，不拋出例外

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 嘗試從郵件 HTML 下載 PDF 帳單。當目標下載系統（`fbmbill.taipeifubon.com.tw` 等）為 SPA + API + 可能 OTP 的架構、自動化流程尚未實作時，SHALL 拋出 `FetchError`，錯誤訊息 MUST 明確說明「FUBON 帳單系統已遷移為 SPA 流程，自動下載尚未實作」，以便 pipeline 將失敗記錄到 JSON summary 與 logs，讓使用者知曉並決定手動處理。

#### Scenario: SPA 網域的下載請求拋出明確 FetchError
- **WHEN** `fetch_pdf()` 被呼叫且 HTML 內含 `fbmbill.taipeifubon.com.tw` 下載連結
- **THEN** SHALL 拋出 `FetchError`，`bank_code="FUBON"`，錯誤訊息包含「SPA」與「尚未實作」字樣

#### Scenario: URL 提取失敗
- **WHEN** HTML body 中找不到任何指向 `_ALLOWED_DOMAINS` 的連結
- **THEN** SHALL 拋出 `FetchError`，包含 `bank_code="FUBON"` 與「找不到帳單下載連結」描述

## REMOVED Requirements

### Requirement: CAPTCHA OCR 工具

**Reason**: FUBON 帳單下載系統已於某時點遷移為 Vue SPA，不再使用 CAPTCHA 圖片驗證（改為 API 流程與可能的 OTP）。`solve_captcha()` 工具本身仍保留在 `ccas.ingestor.fetcher.captcha` 模組中供其他銀行或未來需求使用，但其 requirement 不再屬於 `fubon-fetcher-impl` 規格。

**Migration**: 本變更之後，`fubon-fetcher-impl` 規格不再對 CAPTCHA 有任何要求。呼叫者不應期待 `FubonFetcher` 進行任何 CAPTCHA 辨識。
