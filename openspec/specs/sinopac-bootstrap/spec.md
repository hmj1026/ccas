# sinopac-bootstrap Specification

## Purpose
TBD - created by archiving change add-sinopac-bank-support. Update Purpose after archive.
## Requirements
### Requirement: SINOPAC 銀行設定範本

`banks.example.yaml` SHALL 包含永豐銀行（SINOPAC）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 SINOPAC 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `SINOPAC` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配永豐帳單郵件
- **WHEN** Gmail filter 設定為 `from:ebillservice@newebill.banksinopac.com.tw subject:永豐銀行信用卡 subject:電子帳單通知`
- **THEN** SHALL 能匹配主旨格式為「永豐銀行信用卡YYYY年MM月份電子帳單通知」的郵件

### Requirement: SINOPAC PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_SINOPAC` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 SINOPAC 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_SINOPAC` 的註解說明與範例值

#### Scenario: Settings 可正確取得 SINOPAC 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_SINOPAC` 已設定
- **THEN** `Settings.get_pdf_password("SINOPAC")` SHALL 回傳該值

### Requirement: bank-code-registry 標記 SINOPAC 為 supported

`bank-code-registry.yaml` 中 SINOPAC 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 SINOPAC 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 SINOPAC 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用

