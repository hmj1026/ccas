## MODIFIED Requirements

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
