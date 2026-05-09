# Spec Delta: ESUN Parser

## MODIFIED Requirements

### Requirement: ESUN 帳單識別 SHALL 掃描全部頁面

`EsunV1Parser.can_parse()` MUST 讀取所有頁面並串接為 full_text，若文字中同時包含 `玉山` 與 `信用卡帳單` 則回傳 True。

#### Scenario: 首頁不含「玉山」但其他頁含有

- **GIVEN** 一份 ESUN PDF，首頁只有 `信用卡帳單`，第 3 頁含 `玉山銀行` 扣款說明
- **WHEN** 呼叫 `can_parse(pdf_path)`
- **THEN** 回傳 True

### Requirement: ESUN Summary 擷取 SHALL 支援民國年與 TWD 前綴

`_extract_summary()` MUST 優先以民國年 pattern 抓取帳單月份與繳款截止日，並支援 `TWD` 前綴作為本期應繳總金額的貨幣標示。

#### Scenario: 民國年 billing_month

- **GIVEN** 首頁含 `這是您 115年02月 信用卡帳單`
- **WHEN** 擷取 billing_month
- **THEN** 回傳 `2026-02`（民國 115 轉西元 2026）

#### Scenario: 無標籤民國年 due_date

- **GIVEN** 首頁含 `115/04/07 7.88%`（無「繳款截止日」標籤）
- **WHEN** 擷取 due_date
- **THEN** 回傳 `date(2026, 4, 7)`

#### Scenario: TWD 前綴總金額

- **GIVEN** 任一頁含 `本期應繳總金額： TWD 26,920`
- **WHEN** 擷取 total_amount
- **THEN** 回傳 `26920`

### Requirement: ESUN 交易行擷取 SHALL 支援 MM/DD + TWD 格式

`_extract_transactions()` MUST 支援 `MM/DD  MM/DD  MERCHANT  TWD  AMOUNT` 的文字行格式。

#### Scenario: ESUN 消費行

- **GIVEN** 一行 `02/12 02/23 連加＊連加＊某百貨分店 TWD 142`
- **WHEN** 解析交易
- **THEN** 得到 `TransactionItem(trans_date=date(2026,2,12), posting_date=date(2026,2,23), merchant='連加＊連加＊某百貨分店', amount=142)`

#### Scenario: 退款負額

- **GIVEN** 一行 `03/09 感謝您辦理本行自動轉帳繳款！ TWD -10,615`
- **WHEN** 解析交易
- **THEN** 結果 `amount == -10615`
