# llm-reference-parsing Specification

## Purpose
TBD - created by archiving change harden-bill-parsing-pipeline. Update Purpose after archive.
## Requirements
### Requirement: LLM 參考路徑預設關閉，且由獨立開關控制

系統 SHALL 提供設定項 `BILL_PARSE_LLM_REFERENCE_ENABLED`（預設 `False`），只有在此開關開啟時才會對規則／OCR 失敗或低信心的帳單呼叫 LLM 參考路徑；此開關關閉時規則／OCR route 仍須繼續。

#### Scenario: 開關關閉時不呼叫 LLM

- **WHEN** `BILL_PARSE_LLM_REFERENCE_ENABLED=False` 且某筆帳單規則解析失敗或 OCR 候選低於 `0.85`
- **THEN** 系統 SHALL 不對外發起任何 LLM 呼叫，該筆帳單直接依既有失敗路徑處理（標記 `parse_failed` 或 `needs_review`）

#### Scenario: 開關開啟時才於信心不足時觸發

- **WHEN** `BILL_PARSE_LLM_REFERENCE_ENABLED=True` 且規則／OCR 解析信心低於 `0.85` 或失敗
- **THEN** 系統 SHALL 呼叫 LLM 參考路徑取得候選解析結果

### Requirement: LLM 輸出需通過 schema 與交叉檢查才可採用

系統 SHALL 讓 LLM 參考路徑的輸出先通過 `parse-result-schema` 定義的 schema 驗證，再通過交叉檢查（明細加總 vs 帳單欄位、日期區間合理性、末四碼格式），並且必須滿足全域採用閘門：`parse_confidence >= 0.85` 且 `needs_review=False`。任一項未通過，該輸出 SHALL 保留為候選、不得寫入 `Bill`/`Transaction` 正式欄位，並只能標記為 `needs_review`。

#### Scenario: LLM 輸出通過驗證

- **WHEN** LLM 參考路徑回傳的結構化資料通過 schema 驗證與全部交叉檢查，且 `parse_confidence >= 0.85`、`needs_review=False`
- **THEN** 系統 SHALL 將其視為 `parse_method="llm"` 的正式解析結果並寫入

#### Scenario: LLM 輸出未通過驗證

- **WHEN** LLM 參考路徑回傳的資料未通過交叉檢查（例如明細加總與帳單總額不符）
- **THEN** 系統 SHALL 拒絕將其寫入正式帳務欄位，改標記該帳單 `needs_review=True` 並記錄原因

### Requirement: 沿用既有雲端憑證，不新增第二組秘密

系統 SHALL 讓 LLM 參考路徑沿用既有 `anthropic_api_key`（`SecretStr`）設定，不得新增獨立於既有憑證管理之外的第二組 API 金鑰設定。

#### Scenario: 憑證缺失時的行為

- **WHEN** `BILL_PARSE_LLM_REFERENCE_ENABLED=True` 但 `anthropic_api_key` 未設定
- **THEN** 系統 SHALL 在啟動或首次呼叫時明確記錄設定錯誤，並讓解析流程退回規則／OCR 路徑而非中斷整個 pipeline

### Requirement: 每次呼叫需留下不含內容的稽核紀錄

系統 SHALL 為每次 LLM 參考呼叫記錄一筆結構化 log，至少包含帳單識別資訊與時間戳，SHALL 不包含帳單內容或個資，並沿用既有 `RedactingFilter` 保護。

#### Scenario: 稽核紀錄可回答「哪一筆帳單、何時送出」

- **WHEN** 稽核人員查詢某段時間內的 LLM 參考呼叫紀錄
- **THEN** 系統 SHALL 能提供足以回答「哪些帳單、何時」的結構化 log，且該 log 不含帳單原始內容

### Requirement: LLM 呼叫使用獨立逾時預算

系統 SHALL 為 LLM 參考路徑設定獨立於既有 `PDF_PARSE_TIMEOUT_SECONDS` 的逾時預算，逾時 SHALL 視為該次 LLM 參考失敗，並落回規則／OCR 已得出的結果或標記 `needs_review`，不得拖慢或阻塞其他帳單的處理。

#### Scenario: LLM 呼叫逾時

- **WHEN** LLM 參考呼叫超過其獨立逾時預算
- **THEN** 系統 SHALL 中止該次呼叫、不影響其他帳單的處理進度，並依既有規則／OCR 結果或 `needs_review` 標記處理該筆帳單
