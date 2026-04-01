## ADDED Requirements

### Requirement: CTBC v1 parser 可辨識中國信託帳單格式

系統 SHALL 提供 CTBC v1 parser，透過 `can_parse()` 判斷已解密 PDF 是否為中國信託信用卡帳單。辨識基於第一頁文字中的特徵標記（須同時包含「中國信託」與「信用卡」相關關鍵字），不執行完整解析。

#### Scenario: 辨識 CTBC 帳單

- **WHEN** 收到一份已解密的中國信託信用卡帳單 PDF
- **THEN** `can_parse()` SHALL 回傳 `True`

#### Scenario: 排除非 CTBC 帳單

- **WHEN** 收到一份非中國信託的帳單 PDF（如國泰世華、玉山）
- **THEN** `can_parse()` SHALL 回傳 `False`

#### Scenario: 處理無法開啟的 PDF

- **WHEN** 收到一份損毀或無法開啟的 PDF
- **THEN** `can_parse()` SHALL 回傳 `False`，不拋出例外

### Requirement: CTBC v1 parser 可提取帳單摘要

系統 SHALL 從 CTBC 帳單 PDF 提取帳單月份、應繳總額、繳費截止日三項摘要資訊。

#### Scenario: 成功提取帳單摘要

- **WHEN** 解析一份標準 CTBC 帳單 PDF
- **THEN** `ParseResult` SHALL 包含：
  - `bank_code` 為 `"CTBC"`
  - `billing_month` 為 `"YYYY-MM"` 格式
  - `total_amount` 為正整數（元為單位）
  - `due_date` 為有效日期

#### Scenario: 帳單摘要缺失

- **WHEN** PDF 中找不到繳費截止日或應繳總額
- **THEN** parser SHALL 拋出 `ParseError`，訊息中包含缺失欄位名稱

### Requirement: CTBC v1 parser 可提取交易明細

系統 SHALL 從 CTBC 帳單 PDF 的表格中提取所有交易明細行。

#### Scenario: 成功提取交易明細

- **WHEN** 解析一份含有 N 筆交易的 CTBC 帳單
- **THEN** `ParseResult.transactions` SHALL 包含 N 筆 `TransactionItem`，每筆包含：
  - `trans_date`：交易日期
  - `merchant`：商家名稱
  - `amount`：金額（整數，元為單位）

#### Scenario: 交易包含卡號末四碼

- **WHEN** 帳單交易明細中包含卡號資訊
- **THEN** `TransactionItem.card_last4` SHALL 填入對應的四位數字字串

#### Scenario: 交易包含入帳日期

- **WHEN** 帳單交易明細中包含入帳日期
- **THEN** `TransactionItem.posting_date` SHALL 填入對應日期

### Requirement: CTBC v1 parser 可處理多頁表格

系統 SHALL 正確處理跨頁的交易明細表格，將所有頁面的交易合併為單一 transactions tuple。

#### Scenario: 跨頁交易明細

- **WHEN** 帳單交易明細跨越 2 頁以上
- **THEN** `ParseResult.transactions` SHALL 包含所有頁面的交易，不遺漏跨頁行

### Requirement: CTBC v1 parser 輸出不可變資料

`parse()` 回傳的 `ParseResult` 與其中的 `TransactionItem` SHALL 為不可變物件（frozen dataclass）。

#### Scenario: ParseResult 不可變性

- **WHEN** 嘗試修改 `ParseResult` 或 `TransactionItem` 的屬性
- **THEN** SHALL 拋出 `FrozenInstanceError`

### Requirement: CTBC v1 parser 自動註冊到 registry

CTBC v1 parser 模組被 import 時 SHALL 自動將 parser 實例註冊到全域 registry。

#### Scenario: import 後可被 registry 發現

- **WHEN** import `ccas.parser.banks.ctbc_v1` 模組
- **THEN** `registry.resolve("CTBC")` SHALL 回傳包含 CtbcV1Parser 的候選列表
