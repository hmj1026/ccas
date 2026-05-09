# fubon-parser Specification

## Purpose

定義 `FubonV1Parser.parse()` 從富邦銀行帳單 PDF 提取消費交易明細的契約：每筆交易的必要 / 可選欄位、卡號分組標頭如何傳遞 `card_last4` 給後續交易、merchant 名稱中分期 pattern `(NN/MM期)` 的拆解規則，以及無法解析行的 fail-soft 處理（warning + skip，不中斷整體解析）。

## Requirements

### Requirement: parse 提取交易明細

`FubonV1Parser.parse()` SHALL 從富邦帳單 PDF 提取所有消費交易明細，包含卡號末四碼與分期資訊。

#### Scenario: 成功提取多筆交易
- **WHEN** 帳單 PDF 包含多筆消費明細
- **THEN** `ParseResult.transactions` SHALL 包含對應數量的 `TransactionItem`，每筆含 trans_date、merchant、amount

#### Scenario: 可選欄位正確處理
- **WHEN** 交易行包含入帳日與卡號末四碼
- **THEN** `TransactionItem` SHALL 填入 `posting_date` 與 `card_last4`

#### Scenario: 卡號分組標頭傳遞 card_last4
- **WHEN** PDF 包含卡號分組標頭（如「MASTER鈦金正卡末４碼5273」���
- **THEN** 該標頭下方的所有交易 SHALL 繼承 `card_last4 = "5273"`，直到遇到下一個卡號標頭

#### Scenario: 分期資訊從 merchant 提取
- **WHEN** 交易的 merchant 名稱包含「(NN/MM期)」格式
- **THEN** `TransactionItem` SHALL 設定 `installment_current = NN`、`installment_total = MM`，且 merchant 名稱 SHALL 移除該 suffix

#### Scenario: 無分期資訊的交易不受影響
- **WHEN** merchant 名稱不包含分期 pattern
- **THEN** `installment_current` 與 `installment_total` SHALL 為 None

#### Scenario: 無法解析的交易行被跳過
- **WHEN** 某些交易行格式異常無法解析
- **THEN** parser SHALL 記錄 warning 並跳過該行，不中斷整體解析
