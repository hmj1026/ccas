## MODIFIED Requirements

### Requirement: CTBC v1 parser 可提取交易明細

系統 SHALL 從 CTBC 帳單 PDF 的表格中提取所有交易明細行，包括消費明細載要欄位中的商戶名稱文字。

#### Scenario: 成功提取交易明細

- **WHEN** 解析一份含有 N 筆交易的 CTBC 帳單
- **THEN** `ParseResult.transactions` SHALL 包含 N 筆 `TransactionItem`，每筆包含：
  - `trans_date`：交易日期
  - `merchant`：商家名稱（從消費明細載要欄位提取的文字）
  - `amount`：金額（整數，元為單位）

#### Scenario: 交易包含卡號末四碼

- **WHEN** 帳單交易明細中包含卡號資訊
- **THEN** `TransactionItem.card_last4` SHALL 填入對應的四位數字字串

#### Scenario: 交易包含入帳日期

- **WHEN** 帳單交易明細中包含入帳日期
- **THEN** `TransactionItem.posting_date` SHALL 填入對應日期

#### Scenario: ROC 格式商戶名稱提取

- **WHEN** 解析 ROC 格式（民國年）的 CTBC 帳單
- **THEN** `TransactionItem.merchant` SHALL 從消費明細載要欄位提取文字，不再預設為空字串

#### Scenario: 商戶名稱提取失敗 fallback

- **WHEN** ROC 格式的某筆交易無法提取商戶名稱文字
- **THEN** `TransactionItem.merchant` SHALL fallback 為空字串 `""`，不影響該筆交易的其他欄位提取

### Requirement: 真實 CTBC 帳單端到端解析驗證

系統 SHALL 確保真實 CTBC 帳單 PDF 透過 pipeline 解析後產生完整的資料庫記錄。

#### Scenario: 真實 CTBC 帳單端到端解析驗證

- **WHEN** 透過真實 pipeline 從 Gmail 下載並解密 CTBC 帳單 PDF 後進行解析
- **THEN** DB 中 SHALL 建立 `Bill` 記錄（`bank_code=CTBC`），且對應的 `Transaction` 記錄筆數大於 0，每筆交易的 `amount` 為正整數，`merchant` 欄位 SHALL 包含從消費明細載要提取的文字（允許少數筆因提取失敗為空字串）
