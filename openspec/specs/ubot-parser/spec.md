# ubot-parser Specification

## Purpose
TBD - created by archiving change add-ubot-bank-support. Update Purpose after archive.
## Requirements
### Requirement: UbotV1Parser 實作 BankParser 介面

系統 SHALL 提供 `UbotV1Parser` 類別，繼承 `BankParser`，設定 `bank_code = "UBOT"` 與 `version = "v1"`，並實作 `can_parse()` 與 `parse()` 方法。

#### Scenario: parser 宣告正確的 bank_code 與 version
- **WHEN** 檢查 `UbotV1Parser` 的屬性
- **THEN** `bank_code` SHALL 為 `"UBOT"`，`version` SHALL 為 `"v1"`

### Requirement: can_parse 正確辨識聯邦帳單 PDF

`UbotV1Parser.can_parse()` SHALL 透過掃描 PDF 所有頁面文字辨識聯邦銀行信用卡帳單，支援舊版（含「聯邦銀行」header）與真實新版（僅含「為您XX月份之信用卡」）兩種佈局。

#### Scenario: 辨識舊版聯邦帳單 PDF
- **WHEN** 輸入 PDF 任一頁面包含「聯邦銀行」與「信用卡」關鍵字
- **THEN** `can_parse()` SHALL 回傳 `True`

#### Scenario: 辨識真實新版聯邦帳單 PDF
- **WHEN** 輸入 PDF 任一頁面包含「為您」與「月份之信用卡」關鍵字，即使首頁無「聯邦銀行」字樣
- **THEN** `can_parse()` SHALL 回傳 `True`

#### Scenario: 拒絕非聯邦帳單 PDF
- **WHEN** 輸入 PDF 所有頁面皆不包含聯邦銀行特徵關鍵字
- **THEN** `can_parse()` SHALL 回傳 `False`

#### Scenario: 損壞 PDF 不導致例外
- **WHEN** 輸入 PDF 無法開啟或讀取
- **THEN** `can_parse()` SHALL 回傳 `False`，不拋出例外

### Requirement: UBOT parser SHALL 解析真實 PDF 佈局

`UbotV1Parser._extract_summary` MUST 辨識真實聯邦銀行帳單的無標籤欄位佈局，提取 billing_month、total_amount、due_date。

#### Scenario: 從「為您XX月份」擷取帳單月份
- **GIVEN** 文字含 `以下為您01月份之信用卡消費帳單：` 與結帳日 `115/01/27 2.1% 起`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2026-01"`

#### Scenario: 從「已申請自動轉帳」擷取繳款截止日
- **GIVEN** 文字含 `115/02/11 已申請自動轉帳`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2026, 2, 11)`

#### Scenario: 從「優惠注意事項」錨點擷取本期應繳總額
- **GIVEN** 文字含 `6,850 6,850 4,000,000 優惠注意事項`
- **WHEN** 呼叫 `_extract_total_amount`
- **THEN** 回傳 `6850`（第一欄即本期應繳總額）

### Requirement: UBOT parser SHALL 處理無需繳款零結帳單

當 PDF 文字含 `無需繳款` 標記時，`_extract_summary` MUST 拋出 `ParseError`，`reason` 含 `zero-balance`，由 `parser/job.py` 路由為 `parse_skipped`。

#### Scenario: 無需繳款標記拋出 zero-balance ParseError
- **GIVEN** 文字含 `無需繳款` 與 `為您07月份之信用卡消費帳單`
- **WHEN** 呼叫 `_extract_summary`
- **THEN** 拋出 `ParseError`，`reason` 包含 `"zero-balance"`

### Requirement: UBOT parser SHALL 解析真實交易行格式

`_extract_transactions` MUST 以行為單位解析真實 PDF 的交易格式，支援本地、外幣、負數、行動支付前綴 `+` 與卡號末四碼追蹤。

#### Scenario: 本地交易含國別碼 TW
- **GIVEN** 文字含 `12/30 12/26 某保險公司 ＸＸＸＸＸＸＸＸＸＸＸ TW 12,152`
- **WHEN** 呼叫 `_extract_transactions`（billing_year=2026）
- **THEN** 產生一筆 `TransactionItem`，`amount=12152`

#### Scenario: 外幣交易含 FX 尾綴
- **GIVEN** 文字含 `01/07 12/31 PRIME MEMBERSHIP MEGURO-KU JP 01/02 JPY 600.00 120`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=120`

#### Scenario: 行動支付 + 前綴
- **GIVEN** 文字含 `+ 02/23 02/17 台灣大創百貨（股）南港ＬａＬａｐｏｒｔ TW 98`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=98`

#### Scenario: 負數退款交易
- **GIVEN** 文字含 `12/31 12/26 專案：想分調整某保險公司 ＸＸＸＸ -12,152`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=-12152`

#### Scenario: 卡號末四碼跟隨 header
- **GIVEN** 文字中先出現 `聯邦Ｍ悠遊鈦商卡 －正卡 8000`，之後出現交易行
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 後續交易的 `card_last4` SHALL 為 `"8000"`

### Requirement: parse 提取帳單摘要

`UbotV1Parser.parse()` SHALL 從聯邦帳單 PDF 提取帳單月份（billing_month）、應繳總額（total_amount）、繳費截止日（due_date）。

#### Scenario: 成功提取帳單摘要
- **WHEN** 輸入有效的聯邦帳單 PDF
- **THEN** `ParseResult` SHALL 包含格式為 `"YYYY-MM"` 的 billing_month、整數型 total_amount、date 型 due_date

#### Scenario: 摘要欄位缺失時拋出 ParseError
- **WHEN** PDF 中找不到必要的摘要欄位（月份、金額或到期日）
- **THEN** SHALL 拋出 `ParseError`，包含缺失欄位的說明

### Requirement: parse 提取交易明細

`UbotV1Parser.parse()` SHALL 從聯邦銀行帳單 PDF 提取所有**消費**交易明細，並 MUST NOT 將現金回饋、紅利折抵、退款、沖銷等回補類行納入 `ParseResult.transactions`。回饋行的識別 SHALL 以「merchant 前綴或全字命中 cashback keyword」或「amount < 0」或「原始行首含 `(-)` / 全形 `－` 標記」任一條件成立為判準。

#### Scenario: 成功提取多筆消費

- **WHEN** 帳單 PDF 包含多筆正常消費行
- **THEN** `ParseResult.transactions` SHALL 包含對應數量的 `TransactionItem`

#### Scenario: 現金回饋入帳行被過濾

- **GIVEN** PDF 文字含 `"05/28 現金回饋入帳 -320"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 紅利折抵行被過濾

- **GIVEN** PDF 文字含 `"05/30 紅利折抵 -100"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 負金額行被過濾

- **GIVEN** PDF 文字含 `"06/01 7-ELEVEN -88"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL NOT 出現在 `transactions`

#### Scenario: 正常消費不被誤殺

- **GIVEN** 正常消費行 `"06/02 家樂福 450"`
- **WHEN** parser 處理該行
- **THEN** 該 row SHALL 出現在 `transactions`

#### Scenario: 商家中段含「回饋」字樣不被誤殺

- **GIVEN** 商家字串 `"幸福回饋店"`（keyword 不在前綴）
- **WHEN** `_is_cashback_row` 判斷
- **THEN** 回傳 `False`

### Requirement: parser 自動註冊至 registry

`ubot_v1` 模組載入時 SHALL 自動將 `UbotV1Parser` 實例註冊至 `ParserRegistry`。

#### Scenario: import 後 registry 包含 UBOT parser
- **WHEN** `ccas.parser.banks.ubot_v1` 模組被 import
- **THEN** `registry.resolve("UBOT", "v1")` SHALL 回傳包含 `UbotV1Parser` 的候選列表

#### Scenario: banks/__init__.py 自動 import ubot_v1
- **WHEN** `ccas.parser.banks` 套件被 import
- **THEN** `ubot_v1` 模組 SHALL 被自動載入，確保 parser 註冊生效

