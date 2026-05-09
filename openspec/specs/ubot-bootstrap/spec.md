# ubot-bootstrap Specification

## Purpose
TBD - created by archiving change add-ubot-bank-support. Update Purpose after archive.
## Requirements
### Requirement: UBOT 銀行設定範本

`banks.example.yaml` SHALL 包含聯邦銀行（UBOT）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 UBOT 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `UBOT` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配聯邦帳單郵件
- **WHEN** Gmail filter 設定為 `from:estatement@ebillv2.card.ubot.com.tw subject:聯邦銀行信用卡 subject:電子帳單`
- **THEN** SHALL 能匹配主旨格式為「聯邦銀行信用卡電子帳單」的郵件

### Requirement: UBOT PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_UBOT` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 UBOT 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_UBOT` 的註解說明與範例值

#### Scenario: Settings 可正確取得 UBOT 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_UBOT` 已設定
- **THEN** `Settings.get_pdf_password("UBOT")` SHALL 回傳該值

### Requirement: bank-code-registry 標記 UBOT 為 supported

`bank-code-registry.yaml` 中 UBOT 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 UBOT 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 UBOT 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用

