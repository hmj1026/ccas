# parse-result-schema Specification

## Purpose
TBD - created by archiving change harden-bill-parsing-pipeline. Update Purpose after archive.
## Requirements
### Requirement: 解析結果攜帶方法與信心欄位

系統 SHALL 讓 `ParseResult`（及其序列化後的帳單資料）攜帶 `parse_method`（值為 `rules`｜`ocr`｜`llm`）與 `parse_confidence`（0.0～1.0 浮點數）欄位。所有路徑共用 `0.85` 作為「信心足夠」的固定契約閾值：只有 `parse_confidence >= 0.85` 且 `needs_review=False` 的候選可成為最終結果。信心分數 SHALL 以可重現的欄位證據計算：`field_score = 有效必要帳單欄位數 / 4`（`bank_code`、`billing_month`、`total_amount`、`due_date`），`check_score = 通過的適用交叉檢查數 / 適用交叉檢查總數`（適用檢查包含有交易時的明細加總、可判定時的日期區間與有末四碼時的格式；沒有適用檢查時為 `1.0`），最後以小數點後兩位的 decimal `ROUND_HALF_UP` 規則四捨五入 `0.7 * field_score + 0.3 * check_score`；必要欄位或交叉檢查無法通過時仍須依結果標記 `needs_review` 與原因。既有規則解析（未經 OCR／LLM）在所有必要欄位及交叉檢查通過時 SHALL 產生 `parse_method="rules"`、`parse_confidence=1.0` 作為預設值。

#### Scenario: 既有規則解析的預設值

- **WHEN** 某筆帳單透過既有銀行 parser 規則成功解析，未觸發 OCR 或 LLM
- **THEN** 該筆 `ParseResult` SHALL 帶有 `parse_method="rules"` 且 `parse_confidence=1.0`

#### Scenario: OCR fallback 解析的方法標記

- **WHEN** 某筆帳單透過 OCR fallback 路徑解析成功
- **THEN** 該筆 `ParseResult` SHALL 帶有 `parse_method="ocr"`，且 `parse_confidence` SHALL 反映該次辨識的信心程度（非固定 1.0）

#### Scenario: 低信心分數的計算可重現

- **WHEN** 某候選有 3 個有效必要帳單欄位，且所有適用交叉檢查通過
- **THEN** `field_score` SHALL 為 `0.75`、`check_score` SHALL 為 `1.0`、`parse_confidence` SHALL 為 `0.83`，因此該候選低於 `0.85` 閾值，不得視為最終結果

### Requirement: 需要人工審查的解析結果附帶原因清單

系統 SHALL 讓解析信心低於 `0.85`、或未通過交叉檢查的結果帶有 `needs_review=True` 與非空的 `review_reasons[]`，每個原因為可讀的字串描述。

#### Scenario: 交叉檢查失敗附帶原因

- **WHEN** 解析結果的明細加總與帳單總額欄位不一致
- **THEN** 該筆結果 SHALL 帶有 `needs_review=True`，且 `review_reasons[]` SHALL 包含描述此不一致的原因字串

#### Scenario: 通過所有檢查的結果不需審查

- **WHEN** 解析結果通過 schema 驗證與全部交叉檢查
- **THEN** 該筆結果 SHALL 帶有 `needs_review=False` 且 `review_reasons[]` 為空陣列

#### Scenario: 低於固定閾值附帶原因

- **WHEN** 候選的 `parse_confidence` 為 `0.83`，且沒有其他更高信心候選
- **THEN** 該筆結果 SHALL 帶有 `needs_review=True`，且 `review_reasons[]` SHALL 包含可讀的低信心原因

### Requirement: JSON Schema 以 Pydantic model 衍生，並鎖定同步

系統 SHALL 保留內部 `ParseResult`／`TransactionItem` 的 dataclass 邊界，並提供一個專責的 Pydantic `BillParseResultSchema` model（包含帳單欄位、四個解析中繼資料欄位與巢狀交易欄位）。`schemas/bill_parse_result.schema.json` SHALL 由 `BillParseResultSchema.model_json_schema()` 產生，並以自動化測試保證 checked-in 檔案內容與目前 model 產生的 schema 一致。

#### Scenario: Model 變更後 schema 檔案過期

- **WHEN** `BillParseResultSchema` 或其對應的 `ParseResult` 欄位新增或修改，但 `schemas/bill_parse_result.schema.json` 未同步更新
- **THEN** 對應的同步鎖定測試 SHALL 失敗，阻止該變更在未更新 schema 檔案的情況下通過

### Requirement: 新增欄位不改變既有 parser 呼叫方式

系統 SHALL 讓 `parse_method`/`parse_confidence`/`needs_review`/`review_reasons` 四個欄位皆有預設值，既有 7 家銀行 parser 的 `parse()` 實作 SHALL 不需要修改即可通過既有測試。

#### Scenario: 既有 parser 測試不需修改

- **WHEN** 執行既有 7 家銀行 parser 的既有測試套件
- **THEN** 所有測試 SHALL 維持通過，不需要因新增欄位而修改 parser 實作或測試斷言
