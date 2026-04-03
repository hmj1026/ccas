## MODIFIED Requirements

### Requirement: CTBC v1 parser 可提取交易明細

系統 SHALL 從 CTBC 帳單 PDF 提取所有交易明細行。ROC 格式的商戶名稱 SHALL 透過 OCR 從圖片中提取（tesseract 可用時），不可用時 fallback 為空字串。

#### Scenario: 成功提取交易明細
- **WHEN** 解析一份含有 N 筆交易的 CTBC 帳單
- **THEN** `ParseResult.transactions` SHALL 包含 N 筆 `TransactionItem`，每筆包含：
  - `trans_date`：交易日期
  - `merchant`：商家名稱（OCR 提取或空字串）
  - `amount`：金額（整數，元為單位）

#### Scenario: ROC 格式商戶名稱 OCR 提取
- **WHEN** 解析 ROC 格式帳單且 tesseract 可用
- **THEN** `TransactionItem.merchant` SHALL 包含從商戶圖片 OCR 辨識的文字

#### Scenario: ROC 格式 OCR 不可用 fallback
- **WHEN** 解析 ROC 格式帳單且 tesseract 不可用
- **THEN** `TransactionItem.merchant` SHALL 為空字串 `""`，不影響其他欄位提取

#### Scenario: 交易包含卡號末四碼
- **WHEN** 帳單交易明細中包含卡號資訊
- **THEN** `TransactionItem.card_last4` SHALL 填入對應的四位數字字串

#### Scenario: 交易包含入帳日期
- **WHEN** 帳單交易明細中包含入帳日期
- **THEN** `TransactionItem.posting_date` SHALL 填入對應日期
