# taishin-bootstrap Specification

## Purpose
TBD - created by archiving change add-taishin-bank-support. Update Purpose after archive.
## Requirements
### Requirement: TAISHIN 銀行設定範本

`banks.example.yaml` SHALL 包含台新銀行（TAISHIN）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 TAISHIN 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `TAISHIN` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配台新帳單郵件
- **WHEN** Gmail filter 設定為 `from:webmaster@bhurecv.taishinbank.com.tw subject:台新信用卡電子帳單`
- **THEN** SHALL 能匹配主旨格式為「台新信用卡電子帳單 YYYY年M月」的郵件

### Requirement: TAISHIN PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_TAISHIN` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 TAISHIN 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_TAISHIN` 的註解說明與範例值
- **AND** SHALL 說明密碼組成規則：身分證字號後 2 碼 + 生日月日 4 碼

#### Scenario: Settings 可正確取得 TAISHIN 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_TAISHIN` 已設定
- **THEN** `Settings.get_pdf_password("TAISHIN")` SHALL 回傳該值

### Requirement: bank-code-registry 標記 TAISHIN 為 supported

`bank-code-registry.yaml` 中 TAISHIN 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 TAISHIN 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 TAISHIN 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用

