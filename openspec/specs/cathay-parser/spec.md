# cathay-parser Specification

## Purpose
TBD - created by archiving change add-cathay-bank-support. Update Purpose after archive.
## Requirements
### Requirement: CathayV1Parser 實作 BankParser 介面

系統 SHALL 提供 `CathayV1Parser` 類別，繼承 `BankParser`，設定 `bank_code = "CATHAY"` 與 `version = "v1"`，並實作 `can_parse()` 與 `parse()` 方法。

#### Scenario: parser 宣告正確的 bank_code 與 version
- **WHEN** 檢查 `CathayV1Parser` 的屬性
- **THEN** `bank_code` SHALL 為 `"CATHAY"`，`version` SHALL 為 `"v1"`

### Requirement: can_parse 透過全部頁面辨識國泰世華帳單

`CathayV1Parser.can_parse()` SHALL 掃描 PDF 全部頁面文字辨識國泰世華信用卡帳單，不限於 page 0，以因應真實 PDF page 0 被 CID 字型遮蔽的情境。辨識 keyword 採兩組後援：主要為「國泰」+「信用卡」，備援為「多利金」+「信用卡」（COSTCO 聯名卡回饋，國泰世華獨有）。

#### Scenario: page 0 關鍵字遮蔽但後續頁面可辨識
- **GIVEN** PDF page 0 的 `extract_text()` 不含「國泰」（因收件人姓名 CID 字型）
- **AND** page 1 含「國泰」與「信用卡」
- **WHEN** 呼叫 `can_parse`
- **THEN** 回傳 `True`

#### Scenario: Ancient PDF 僅含「多利金」備援關鍵字
- **GIVEN** PDF 全部頁面皆不含「國泰」但含「多利金」與「信用卡」
- **WHEN** 呼叫 `can_parse`
- **THEN** 回傳 `True`

#### Scenario: 全部頁面皆無關鍵字
- **WHEN** 所有頁面文字皆不含兩組 keyword
- **THEN** `can_parse` 回傳 `False`

#### Scenario: 損壞 PDF 不導致例外
- **WHEN** 輸入 PDF 無法開啟或讀取
- **THEN** `can_parse` 回傳 `False`，不拋出例外

### Requirement: CATHAY parser SHALL 解析多版帳單 summary 佈局

`CathayV1Parser._extract_summary` MUST 支援跨版本 billing_month / due_date 錨點組合：`以下為您YYY年MM月份`、`信用卡帳單 YYY年MM月`、grid 結帳日並排、`繳款截止日(遇假日順延) ROC/MM/DD`、`帳款將於 ROC/MM/DD`。

#### Scenario: 舊版「以下為您YYY年MM月份」月份錨點
- **GIVEN** 文字含 `以下為您108年5月份的信用卡電子帳單`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2019-05"`

#### Scenario: 新版「信用卡帳單 YYY年MM月」月份錨點
- **GIVEN** 文字含 `信用卡帳單 115年3月`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2026-03"`

#### Scenario: Grid 佈局從結帳日並排推導月份
- **GIVEN** 文字含獨立行 `112/03/15 112/04/01`
- **AND** 無「信用卡帳單」或「以下為您」錨點
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2023-03"`（第一組日期即結帳日）

#### Scenario: 「繳款截止日(遇假日順延)」無冒號錨點
- **GIVEN** 文字含 `繳款截止日(遇假日順延) 108/06/01`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2019, 6, 1)`

#### Scenario: 「帳款將於」扣款日錨點
- **GIVEN** 文字含 `您的新臺幣帳款將於 115/04/01 (遇假日順延)`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2026, 4, 1)`

### Requirement: parse 提取帳單摘要

`CathayV1Parser.parse()` SHALL 從國泰世華帳單 PDF 提取帳單月份（billing_month）、應繳總額（total_amount）、繳費截止日（due_date）。

#### Scenario: 成功提取帳單摘要
- **WHEN** 輸入有效的國泰世華帳單 PDF
- **THEN** `ParseResult` SHALL 包含格式為 `"YYYY-MM"` 的 billing_month、整數型 total_amount、date 型 due_date

#### Scenario: 摘要欄位缺失時拋出 ParseError
- **WHEN** PDF 中找不到必要的摘要欄位（月份、金額或到期日）
- **THEN** SHALL 拋出 `ParseError`，包含缺失欄位的說明

### Requirement: parse 提取交易明細

`CathayV1Parser.parse()` SHALL 從國泰世華帳單 PDF 提取所有**真正的消費交易**明細，並 MUST NOT 將「帳單分期資訊」、「紅利點數」、「優惠回饋」等非交易段落內的數字/日期組合誤判為交易。表格擷取路徑 MUST 接受 CATHAY 實際使用的多種 header 用字（新版「交易日/入帳日/新臺幣金額」與舊版「消費日/金額」等），以 keyword set 取代單一關鍵字硬比對。

#### Scenario: 成功提取多筆交易

- **WHEN** 帳單 PDF 包含多筆消費明細
- **THEN** `ParseResult.transactions` SHALL 包含對應數量的 `TransactionItem`，每筆含 trans_date、merchant、amount

#### Scenario: 可選欄位正確處理

- **WHEN** 交易行包含入帳日與卡號末四碼
- **THEN** `TransactionItem` SHALL 填入 `posting_date` 與 `card_last4`

#### Scenario: 無法解析的交易行被跳過

- **WHEN** 某些交易行格式異常無法解析
- **THEN** parser SHALL 記錄 warning 並跳過該行，不中斷整體解析

#### Scenario: 帳單分期資訊段不得被誤判為交易

- **GIVEN** PDF 文字中消費明細區之後接著「帳單分期資訊」段落，且該段含形如 `帳單分期 12-12 33,293 2,774 6.00%` 的列
- **WHEN** `_extract_transactions_text` 掃描該頁文字
- **THEN** 分期段落的任何 row SHALL NOT 被轉為 `TransactionItem`，且 `TransactionItem.merchant` 不得包含字串 `帳單分期`

#### Scenario: 紅利點數/優惠回饋段落被忽略

- **GIVEN** PDF 含「紅利點數」或「優惠回饋」或「本期回饋」段落
- **WHEN** 交易擷取邏輯掃描該頁
- **THEN** 該些段落內的所有行 SHALL NOT 出現在 `ParseResult.transactions`

#### Scenario: 多期歷史 PDF 回歸

- **GIVEN** 同時提供 106、108、112、115 年的 CATHAY 帳單 PDF 各一份
- **WHEN** 分別執行 `parse()`
- **THEN** 每一份的 `ParseResult.transactions` SHALL 至少包含 1 筆有效 `TransactionItem`，且所有 `TransactionItem.trans_date` SHALL 落在該帳單的 billing_month 的 6 個月窗口內

#### Scenario: 表格 header 使用 CATHAY 實際用字

- **GIVEN** 某 PDF 的交易表 header 為 `["消費日", "消費明細", "金額"]`（舊版 3 欄）
- **WHEN** `_is_transaction_table` 檢查該 header
- **THEN** SHALL 回傳 `True`，使該表交由 `_parse_transaction_row` 處理

#### Scenario: 非交易表不被誤判

- **GIVEN** 某 PDF 的 `本期應繳分析` 表 header 為 `["項目", "金額"]`（只有 amount-ish，無 date-ish）
- **WHEN** `_is_transaction_table` 檢查該 header
- **THEN** SHALL 回傳 `False`

### Requirement: parser 自動註冊至 registry

`cathay_v1` 模組載入時 SHALL 自動將 `CathayV1Parser` 實例註冊至 `ParserRegistry`。

#### Scenario: import 後 registry 包含 CATHAY parser
- **WHEN** `ccas.parser.banks.cathay_v1` 模組被 import
- **THEN** `registry.resolve("CATHAY", "v1")` SHALL 回傳包含 `CathayV1Parser` 的候選列表

#### Scenario: banks/__init__.py 自動 import cathay_v1
- **WHEN** `ccas.parser.banks` 套件被 import
- **THEN** `cathay_v1` 模組 SHALL 被自動載入，確保 parser 註冊生效

