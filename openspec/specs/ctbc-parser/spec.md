# ctbc-parser Specification

## Purpose
TBD - created by archiving change ctbc-parser-v1. Update Purpose after archive.
## Requirements
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

#### Scenario: 真實 CTBC 帳單端到端解析驗證

- **WHEN** 透過真實 pipeline 從 Gmail 下載並解密 CTBC 帳單 PDF 後進行解析
- **THEN** DB 中 SHALL 建立 `Bill` 記錄（`bank_code=CTBC`），且對應的 `Transaction` 記錄筆數大於 0，每筆交易的 `amount` 為正整數。`merchant` 可為空字串（真實 CTBC PDF 的商家名稱為圖片，無法由 pdfplumber 提取）

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

### Requirement: CTBC OCR 後處理校正商家名稱

系統 SHALL 對 CTBC parser 從 tesseract OCR 取得的商家名稱字串套用字元校正，至少涵蓋兩類：(1) ASCII 字元之間的「一」字正規化為 hyphen `-`；(2) 品牌關鍵字白名單替換（如「百鋼」→「百貨」、「鐵包」→「購物卡」等 CTBC 常見誤辨）。校正 MUST 僅影響 CTBC parser，MUST NOT 變更其他銀行 parser 或 shared OCR helper。

#### Scenario: ASCII-anchored hyphen 正規化

- **GIVEN** OCR 回傳字串 `"ICP一統一超商"` 或 `"網路家庭分期01一06"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 為 `"ICP-統一超商"` / `"網路家庭分期01-06"`

#### Scenario: 中文 context 的「一」字不被動到

- **GIVEN** OCR 回傳字串 `"統一超商門市"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 仍為 `"統一超商門市"`（「一」兩側非 ASCII，不替換）

#### Scenario: 品牌白名單替換

- **GIVEN** OCR 回傳字串 `"統一時代百鋼台北店"`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 為 `"統一時代百貨台北店"`

#### Scenario: 白名單先於 hyphen 正規化

- **GIVEN** 白名單含 `"X一Mart" → "X-Mart"` 同時 hyphen 規則也會 match
- **WHEN** `normalize_ocr_merchant` 處理 `"X一Mart"`
- **THEN** 最終結果 SHALL 只命中白名單一次，不疊加雙重轉換

#### Scenario: 空字串不變

- **GIVEN** OCR fallback 回傳 `""`
- **WHEN** `normalize_ocr_merchant` 處理該字串
- **THEN** 回傳值 SHALL 仍為 `""`，且不拋例外

#### Scenario: CTBC parser 呼叫點

- **WHEN** `CtbcV1Parser.parse()` 從 OCR 取得 merchant 字串並即將構造 `TransactionItem`
- **THEN** 字串 SHALL 先經 `normalize_ocr_merchant` 處理再寫入 `TransactionItem.merchant`

#### Scenario: 其他銀行不受影響

- **WHEN** `CathayV1Parser.parse()` 處理 merchant 字串
- **THEN** `normalize_ocr_merchant` SHALL NOT 被呼叫，該字串 SHALL 不經 CTBC 專屬校正

