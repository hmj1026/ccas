# esun-bootstrap Specification

## Purpose
TBD - created by archiving change add-esun-bank-support. Update Purpose after archive.
## Requirements
### Requirement: ESUN 銀行設定範本

`banks.example.yaml` SHALL 包含玉山銀行（ESUN）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 ESUN 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `ESUN` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配玉山帳單郵件
- **WHEN** Gmail filter 設定為 `from:estatement@esunbank.com subject:玉山銀行 subject:信用卡電子帳單`
- **THEN** SHALL 能匹配主旨格式為「玉山銀行YYYY年MM月信用卡電子帳單」的郵件

### Requirement: ESUN PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_ESUN` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 ESUN 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_ESUN` 的註解說明與範例值

#### Scenario: Settings 可正確取得 ESUN 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_ESUN` 已設定
- **THEN** `Settings.get_pdf_password("ESUN")` SHALL 回傳該值

### Requirement: bank-code-registry 標記 ESUN 為 supported

`bank-code-registry.yaml` 中 ESUN 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 ESUN 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 ESUN 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用

