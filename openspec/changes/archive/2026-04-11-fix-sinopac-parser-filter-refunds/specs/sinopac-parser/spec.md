## MODIFIED Requirements

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
