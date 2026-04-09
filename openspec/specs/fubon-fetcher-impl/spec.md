# fubon-fetcher-impl Specification

## Purpose
TBD - created by archiving change add-fubon-bank-support. Update Purpose after archive.
## Requirements
### Requirement: FubonFetcher 實作 BankFetcher 介面

系統 SHALL 提供 `FubonFetcher` 類別，繼承 `BankFetcher`，設定 `bank_code = "FUBON"`。

#### Scenario: fetcher 宣告正確的 bank_code
- **WHEN** 檢查 `FubonFetcher` 的屬性
- **THEN** `bank_code` SHALL 為 `"FUBON"`

### Requirement: can_fetch 辨識富邦下載連結

`FubonFetcher.can_fetch()` SHALL 從郵件 HTML body 中偵測「下載帳單明細」連結。

#### Scenario: 包含下載連結的郵件
- **WHEN** HTML body 包含「下載帳單明細」相關連結（`<a>` 標籤或按鈕）
- **THEN** `can_fetch()` SHALL 回傳 `True`

#### Scenario: 不包含下載連結的郵件
- **WHEN** HTML body 不包含富邦帳單下載相關連結
- **THEN** `can_fetch()` SHALL 回傳 `False`

#### Scenario: 空或無效 HTML 不導致例外
- **WHEN** HTML body 為 None、空字串或無效 HTML
- **THEN** `can_fetch()` SHALL 回傳 `False`，不拋出例外

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 從郵件 HTML 提取 URL、與 web 表單互動、下載 PDF。

#### Scenario: 成功下載 PDF
- **WHEN** 提供有效的 HTML body 與正確憑證
- **THEN** SHALL 完成以下步驟：
  1. 從 HTML body 提取「下載帳單明細」URL
  2. 以 HTTP client 訪問該 URL
  3. 從頁面提取表單欄位與 CAPTCHA 圖片
  4. OCR 辨識 CAPTCHA
  5. 填入身分證字號（credentials["national_id"]）、民國生日（credentials["roc_birthday"]）、CAPTCHA 值
  6. 提交表單
  7. 回傳 PDF 檔案位元組

#### Scenario: URL 提取失敗
- **WHEN** HTML body 中找不到下載 URL
- **THEN** SHALL 拋出 `FetchError`，包含 bank_code="FUBON" 與失敗描述

#### Scenario: CAPTCHA OCR 失敗後重試
- **WHEN** 表單提交因 CAPTCHA 錯誤被拒絕
- **THEN** SHALL 自動重試（重新取得 CAPTCHA 圖片、OCR、提交），最多重試 3 次
- **AND** 每次重試 SHALL 記錄 warning log

#### Scenario: 所有重試耗盡
- **WHEN** CAPTCHA 重試 3 次仍失敗
- **THEN** SHALL 拋出 `FetchError`，包含 "CAPTCHA 辨識失敗" 描述

### Requirement: CAPTCHA OCR 工具

系統 SHALL 提供 `solve_captcha(image_bytes: bytes) -> str` 工具函式。

#### Scenario: 辨識英數驗證碼圖片
- **WHEN** 輸入簡單英數驗證碼圖片
- **THEN** SHALL 使用 pytesseract（`--psm 7` 單行模式 + 英數字元白名單）回傳辨識文字

#### Scenario: 辨識失敗回傳空字串
- **WHEN** 輸入無法辨識的圖片
- **THEN** SHALL 回傳空字串，不拋出例外

#### Scenario: tesseract 不可用時 graceful 降級
- **WHEN** 系統未安裝 tesseract
- **THEN** SHALL 拋出 `FetchError`，說明 CAPTCHA OCR 需要 tesseract

### Requirement: FubonFetcher 自動註冊至 FetcherRegistry

`fubon` 模組載入時 SHALL 自動將 `FubonFetcher` 實例註冊至 `FetcherRegistry`。

#### Scenario: import 後 registry 包含 FUBON fetcher
- **WHEN** `ccas.ingestor.fetcher.banks.fubon` 模組被 import
- **THEN** `fetcher_registry.get("FUBON")` SHALL 回傳 `FubonFetcher` 實例

