## ADDED Requirements

### Requirement: FUBON 銀行設定範本

`banks.example.yaml` SHALL 包含台北富邦銀行（FUBON）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 FUBON 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `FUBON` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配富邦帳單郵件
- **WHEN** Gmail filter 設定為 `from:rs@cf.taipeifubon.com.tw subject:台北富邦銀行 subject:信用卡帳單`
- **THEN** SHALL 能匹配主旨格式為「台北富邦銀行YYYY年M月信用卡帳單」的郵件（含有附件與無附件兩種格式）

### Requirement: FUBON PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_FUBON` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 FUBON 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_FUBON` 的註解說明與範例值
- **AND** SHALL 說明密碼組成規則：身分證字號

#### Scenario: Settings 可正確取得 FUBON 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_FUBON` 已設定
- **THEN** `Settings.get_pdf_password("FUBON")` SHALL 回傳該值

### Requirement: FUBON Web-Fetch 憑證環境變數

`.env.example` SHALL 包含 `FUBON_NATIONAL_ID` 與 `FUBON_ROC_BIRTHDAY` 環境變數範例。

#### Scenario: 環境變數範例中包含 FUBON web-fetch 憑證
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `FUBON_NATIONAL_ID` 與 `FUBON_ROC_BIRTHDAY` 的註解說明
- **AND** SHALL 說明民國生日格式為 7 碼（如 `0881010` 表示民國 68 年 10 月 26 日）

#### Scenario: Settings 可正確取得 FUBON 憑證
- **WHEN** 環境變數 `FUBON_NATIONAL_ID` 與 `FUBON_ROC_BIRTHDAY` 已設定
- **THEN** `Settings.get_bank_credential("FUBON", "NATIONAL_ID")` SHALL 回傳身分證字號
- **AND** `Settings.get_bank_credential("FUBON", "ROC_BIRTHDAY")` SHALL 回傳民國生日

### Requirement: bank-code-registry 標記 FUBON 為 supported

`bank-code-registry.yaml` 中 FUBON 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 FUBON 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 FUBON 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用且支援 web-fetch
