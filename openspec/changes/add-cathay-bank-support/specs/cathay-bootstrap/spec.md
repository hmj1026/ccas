## ADDED Requirements

### Requirement: CATHAY 銀行設定範本

`banks.example.yaml` SHALL 包含國泰世華銀行（CATHAY）的完整銀行配置範本。

#### Scenario: banks.example.yaml 包含 CATHAY 設定
- **WHEN** 使用者查看 `banks.example.yaml`
- **THEN** SHALL 包含 bank_code 為 `CATHAY` 的設定項目，含 gmail_filter、active_parser_version、is_active 欄位

#### Scenario: Gmail filter 正確匹配國泰世華帳單郵件
- **WHEN** Gmail filter 設定為 `from:service@pxbillrc01.cathaybk.com.tw subject:國泰世華銀行信用卡 subject:電子帳單`
- **THEN** SHALL 能匹配主旨格式為「國泰世華銀行信用卡YYYY年M月電子帳單」的郵件

### Requirement: CATHAY PDF 密碼環境變數

`.env.example` SHALL 包含 `PDF_PASSWORD_CATHAY` 環境變數範例，遵循 `PDF_PASSWORD_{BANK_CODE}` 命名模式。

#### Scenario: 環境變數範例中包含 CATHAY 密碼設定
- **WHEN** 使用者查看 `.env.example`
- **THEN** SHALL 看到 `PDF_PASSWORD_CATHAY` 的註解說明與範例值
- **AND** SHALL 說明密碼組成規則：身分證字號

#### Scenario: Settings 可正確取得 CATHAY 密碼
- **WHEN** 環境變數 `PDF_PASSWORD_CATHAY` 已設定
- **THEN** `Settings.get_pdf_password("CATHAY")` SHALL 回傳該值

### Requirement: bank-code-registry 標記 CATHAY 為 supported

`bank-code-registry.yaml` 中 CATHAY 的 `supported` 欄位 SHALL 設為 `true`。

#### Scenario: registry 反映 CATHAY 已支援
- **WHEN** 查看 `bank-code-registry.yaml` 的 CATHAY 項目
- **THEN** `supported` SHALL 為 `true`，`notes` SHALL 更新為反映 v1 parser 可用
