# sinopac-parser Specification

## Purpose
TBD - created by archiving change add-sinopac-bank-support. Update Purpose after archive.
## Requirements
### Requirement: SinopacV1Parser 實作 BankParser 介面

系統 SHALL 提供 `SinopacV1Parser` 類別，繼承 `BankParser`，設定 `bank_code = "SINOPAC"` 與 `version = "v1"`，並實作 `can_parse()` 與 `parse()` 方法。

#### Scenario: parser 宣告正確的 bank_code 與 version
- **WHEN** 檢查 `SinopacV1Parser` 的屬性
- **THEN** `bank_code` SHALL 為 `"SINOPAC"`，`version` SHALL 為 `"v1"`

### Requirement: can_parse 正確辨識永豐帳單 PDF

`SinopacV1Parser.can_parse()` SHALL 透過 PDF 首頁文字特徵辨識永豐銀行信用卡帳單。

#### Scenario: 辨識永豐銀行帳單 PDF
- **WHEN** 輸入 PDF 首頁包含「永豐銀行」與「信用卡」關鍵字
- **THEN** `can_parse()` SHALL 回傳 `True`

#### Scenario: 拒絕非永豐帳單 PDF
- **WHEN** 輸入 PDF 首頁不包含永豐銀行特徵關鍵字
- **THEN** `can_parse()` SHALL 回傳 `False`

#### Scenario: 損壞 PDF 不導致例外
- **WHEN** 輸入 PDF 無法開啟或讀取
- **THEN** `can_parse()` SHALL 回傳 `False`，不拋出例外

### Requirement: parse 提取帳單摘要

`SinopacV1Parser.parse()` SHALL 從永豐帳單 PDF 提取帳單月份（billing_month）、應繳總額（total_amount）、繳費截止日（due_date）。

#### Scenario: 成功提取帳單摘要
- **WHEN** 輸入有效的永豐帳單 PDF
- **THEN** `ParseResult` SHALL 包含格式為 `"YYYY-MM"` 的 billing_month、整數型 total_amount、date 型 due_date

#### Scenario: 摘要欄位缺失時拋出 ParseError
- **WHEN** PDF 中找不到必要的摘要欄位（月份、金額或到期日）
- **THEN** SHALL 拋出 `ParseError`，包含缺失欄位的說明

### Requirement: parse 提取交易明細

`SinopacV1Parser.parse()` SHALL 從永豐帳單 PDF 提取所有**消費**交易明細，並 MUST NOT 將退款、退費、沖銷、取消授權等負值或回補類行納入 `ParseResult.transactions`。退款行的識別 SHALL 以「merchant 前綴或全字命中 refund keyword」或「amount < 0」或「原始行首含 `(-)` / 全形 `－` 標記」任一條件成立為判準。

#### Scenario: 成功提取多筆消費

- **WHEN** 帳單 PDF 包含多筆正常消費行
- **THEN** `ParseResult.transactions` SHALL 包含對應數量的 `TransactionItem`

#### Scenario: 退款 keyword 行被過濾

- **GIVEN** PDF 文字含 `"05/10 退款-網路購物 -1,234"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 負金額行被過濾

- **GIVEN** PDF 文字含 `"05/12 7-ELEVEN -120"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 行首 `(-)` 標記行被過濾

- **GIVEN** PDF 文字含 `"(-)05/15 XX商店 500"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 正常消費不被誤殺

- **GIVEN** PDF 文字含 `"05/20 全家便利商店 85"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL 出現在 `transactions`

#### Scenario: 商家中段含「退」字不被誤殺

- **GIVEN** 商家字串 `"退一步咖啡"`（refund keyword 不在前綴）
- **WHEN** `_is_refund_row` 判斷
- **THEN** 回傳 `False`

### Requirement: parser 自動註冊至 registry

`sinopac_v1` 模組載入時 SHALL 自動將 `SinopacV1Parser` 實例註冊至 `ParserRegistry`。

#### Scenario: import 後 registry 包含 SINOPAC parser
- **WHEN** `ccas.parser.banks.sinopac_v1` 模組被 import
- **THEN** `registry.resolve("SINOPAC", "v1")` SHALL 回傳包含 `SinopacV1Parser` 的候選列表

#### Scenario: banks/__init__.py 自動 import sinopac_v1
- **WHEN** `ccas.parser.banks` 套件被 import
- **THEN** `sinopac_v1` 模組 SHALL 被自動載入，確保 parser 註冊生效

