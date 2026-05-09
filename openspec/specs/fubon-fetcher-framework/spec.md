# fubon-fetcher-framework Specification

## Purpose
TBD - created by archiving change add-fubon-bank-support. Update Purpose after archive.
## Requirements
### Requirement: BankFetcher 抽象介面

系統 SHALL 提供 `BankFetcher` 抽象基底類別，定義 web-fetch 銀行帳單 PDF 的統一合約。

#### Scenario: BankFetcher 定義 can_fetch 與 fetch_pdf 方法
- **WHEN** 檢查 `BankFetcher` 抽象介面
- **THEN** SHALL 定義 `bank_code: str` 屬性
- **AND** SHALL 定義 `can_fetch(html_body: str) -> bool` 抽象方法
- **AND** SHALL 定義 `fetch_pdf(html_body: str, credentials: dict[str, str]) -> bytes` 抽象方法

#### Scenario: FetchError 錯誤類別
- **WHEN** web-fetch 過程中發生錯誤（URL 提取失敗、表單提交失敗、CAPTCHA 辨識失敗）
- **THEN** SHALL 拋出 `FetchError`，繼承自 `CcasError`，包含 bank_code 與錯誤描述

### Requirement: FetcherRegistry 管理 BankFetcher 實例

系統 SHALL 提供 `FetcherRegistry` 單例，管理 `BankFetcher` 的註冊與查找。

#### Scenario: 註冊 fetcher
- **WHEN** 呼叫 `fetcher_registry.register(fetcher_instance)`
- **THEN** registry SHALL 以 `fetcher.bank_code` 為 key 儲存該實例

#### Scenario: 查找 fetcher
- **WHEN** 呼叫 `fetcher_registry.get("FUBON")`
- **AND** FUBON fetcher 已註冊
- **THEN** SHALL 回傳 `FubonFetcher` 實例

#### Scenario: 未註冊的銀行回傳 None
- **WHEN** 呼叫 `fetcher_registry.get("CTBC")`
- **AND** CTBC 無註冊 fetcher
- **THEN** SHALL 回傳 `None`

### Requirement: GmailMessage 支援 HTML body

`GmailMessage` dataclass SHALL 新增 `html_body: str | None` 欄位。

#### Scenario: 有附件的郵件 html_body 為 None
- **WHEN** 郵件含有 PDF 附件
- **THEN** `GmailMessage.html_body` SHALL 為 `None`（避免不必要的 HTML 解析開銷）

#### Scenario: 無附件的郵件填充 html_body
- **WHEN** 郵件不含 PDF 附件
- **THEN** `GmailMessage.html_body` SHALL 包含郵件 HTML body 內容

### Requirement: search_messages 回傳無附件郵件

`search_messages()` SHALL 不再過濾無 PDF 附件的郵件，改為回傳所有匹配郵件。

#### Scenario: 搜尋結果包含無附件郵件
- **WHEN** Gmail 搜尋結果包含有附件與無附件的郵件
- **THEN** `search_messages()` SHALL 回傳所有郵件
- **AND** 無附件郵件的 `pdf_attachments` 為空 tuple，`html_body` 填充 HTML 內容

#### Scenario: 既有行為不受影響
- **WHEN** 郵件含有 PDF 附件
- **THEN** `GmailMessage.pdf_attachments` 仍正確填充
- **AND** `html_body` 為 `None`（與舊行為一致，附件郵件不需 HTML body）

### Requirement: ingest job 支援 web-fetch 路徑

`run_ingestion_job()` SHALL 在處理每封郵件時，除了既有的附件下載路徑，新增 web-fetch 路徑。

#### Scenario: 有附件郵件走既有路徑
- **WHEN** 郵件含有 PDF 附件
- **THEN** SHALL 呼叫既有的 `_process_attachment()` 處理（行為不變）

#### Scenario: 無附件郵件且有對應 fetcher 走 web-fetch 路徑
- **WHEN** 郵件不含 PDF 附件
- **AND** 該銀行在 `FetcherRegistry` 中有註冊 fetcher
- **AND** `fetcher.can_fetch(message.html_body)` 回傳 `True`
- **THEN** SHALL 呼叫 `_process_web_fetch()` 處理
- **AND** 成功下載的 PDF 建立 `StagedAttachment`（status="staged"、source_type="web_fetch"）

#### Scenario: 無附件郵件且無對應 fetcher 被靜默跳過
- **WHEN** 郵件不含 PDF 附件
- **AND** 該銀行在 `FetcherRegistry` 中無註冊 fetcher
- **THEN** SHALL 靜默跳過（與舊行為一致）

### Requirement: StagedAttachment 追蹤來源類型

`StagedAttachment` model SHALL 新增 `source_type` 欄位。

#### Scenario: 既有附件來源
- **WHEN** 透過 Gmail 附件下載建立 StagedAttachment
- **THEN** `source_type` SHALL 為 `"attachment"`（server_default，向後相容）

#### Scenario: web-fetch 來源
- **WHEN** 透過 web-fetch 下載建立 StagedAttachment
- **THEN** `source_type` SHALL 為 `"web_fetch"`

#### Scenario: web-fetch 的 gmail_attachment_id
- **WHEN** 透過 web-fetch 建立 StagedAttachment
- **THEN** `gmail_attachment_id` SHALL 使用合成值 `"web_fetch_{message_id}"` 以維持 unique constraint

### Requirement: Settings 支援銀行專屬憑證

`Settings` SHALL 新增 `get_bank_credential(bank_code, key)` 方法。

#### Scenario: 取得銀行憑證
- **WHEN** 環境變數 `FUBON_NATIONAL_ID` 已設定
- **THEN** `Settings.get_bank_credential("FUBON", "NATIONAL_ID")` SHALL 回傳該值

#### Scenario: 未設定的憑證回傳 None
- **WHEN** 環境變數 `FUBON_NATIONAL_ID` 未設定
- **THEN** `Settings.get_bank_credential("FUBON", "NATIONAL_ID")` SHALL 回傳 `None`

