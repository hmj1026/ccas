## ADDED Requirements

### Requirement: TaishinV1Parser 實作 BankParser 介面

系統 SHALL 提供 `TaishinV1Parser` 類別，繼承 `BankParser`，設定 `bank_code = "TAISHIN"` 與 `version = "v1"`，並實作 `can_parse()` 與 `parse()` 方法。

#### Scenario: parser 宣告正確的 bank_code 與 version
- **WHEN** 檢查 `TaishinV1Parser` 的屬性
- **THEN** `bank_code` SHALL 為 `"TAISHIN"`，`version` SHALL 為 `"v1"`

### Requirement: can_parse 正確辨識台新帳單 PDF

`TaishinV1Parser.can_parse()` SHALL 透過 PDF 首頁文字特徵辨識台新銀行信用卡帳單。

#### Scenario: 辨識台新銀行帳單 PDF
- **WHEN** 輸入 PDF 首頁包含「台新」與「信用卡」關鍵字
- **THEN** `can_parse()` SHALL 回傳 `True`

#### Scenario: 拒絕非台新帳單 PDF
- **WHEN** 輸入 PDF 首頁不包含台新銀行特徵關鍵字
- **THEN** `can_parse()` SHALL 回傳 `False`

#### Scenario: 損壞 PDF 不導致例外
- **WHEN** 輸入 PDF 無法開啟或讀取
- **THEN** `can_parse()` SHALL 回傳 `False`，不拋出例外

### Requirement: parse 提取帳單摘要

`TaishinV1Parser.parse()` SHALL 從台新帳單 PDF 提取帳單月份（billing_month）、應繳總額（total_amount）、繳費截止日（due_date）。

#### Scenario: 成功提取帳單摘要
- **WHEN** 輸入有效的台新帳單 PDF
- **THEN** `ParseResult` SHALL 包含格式為 `"YYYY-MM"` 的 billing_month、整數型 total_amount、date 型 due_date

#### Scenario: 摘要欄位缺失時拋出 ParseError
- **WHEN** PDF 中找不到必要的摘要欄位（月份、金額或到期日）
- **THEN** SHALL 拋出 `ParseError`，包含缺失欄位的說明

### Requirement: parse 提取交易明細

`TaishinV1Parser.parse()` SHALL 從台新帳單 PDF 提取所有消費交易明細。

#### Scenario: 成功提取多筆交易
- **WHEN** 帳單 PDF 包含多筆消費明細
- **THEN** `ParseResult.transactions` SHALL 包含對應數量的 `TransactionItem`，每筆含 trans_date、merchant、amount

#### Scenario: 可選欄位正確處理
- **WHEN** 交易行包含入帳日與卡號末四碼
- **THEN** `TransactionItem` SHALL 填入 `posting_date` 與 `card_last4`

#### Scenario: 無法解析的交易行被跳過
- **WHEN** 某些交易行格式異常無法解析
- **THEN** parser SHALL 記錄 warning 並跳過該行，不中斷整體解析

### Requirement: parser 自動註冊至 registry

`taishin_v1` 模組載入時 SHALL 自動將 `TaishinV1Parser` 實例註冊至 `ParserRegistry`。

#### Scenario: import 後 registry 包含 TAISHIN parser
- **WHEN** `ccas.parser.banks.taishin_v1` 模組被 import
- **THEN** `registry.resolve("TAISHIN", "v1")` SHALL 回傳包含 `TaishinV1Parser` 的候選列表

#### Scenario: banks/__init__.py 自動 import taishin_v1
- **WHEN** `ccas.parser.banks` 套件被 import
- **THEN** `taishin_v1` 模組 SHALL 被自動載入，確保 parser 註冊生效
