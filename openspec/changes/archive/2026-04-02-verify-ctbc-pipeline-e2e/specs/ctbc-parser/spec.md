## MODIFIED Requirements

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

#### Scenario: 真實 CTBC 帳單端到端解析驗證

- **WHEN** 透過真實 pipeline 從 Gmail 下載並解密 CTBC 帳單 PDF 後進行解析
- **THEN** DB 中 SHALL 建立 `Bill` 記錄（`bank_code=CTBC`），且對應的 `Transaction` 記錄筆數大於 0，每筆交易的 `amount` 為正整數。`merchant` 可為空字串（真實 CTBC PDF 的商家名稱為圖片，無法由 pdfplumber 提取）
