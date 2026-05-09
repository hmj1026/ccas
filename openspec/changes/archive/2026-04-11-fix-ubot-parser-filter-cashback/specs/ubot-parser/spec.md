## MODIFIED Requirements

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
