# parse-orchestration Specification

## Purpose
TBD - created by archiving change parser-engine. Update Purpose after archive.
## Requirements
### Requirement: 只處理尚未完成解析的 staged attachment
系統 SHALL 只對尚未標記為成功解析的 staged attachment 執行 parser orchestration，避免重複處理已完成項目。

#### Scenario: 已成功解析的附件會被略過
- **WHEN** 某個 staged attachment 已被標記為 `parsed`
- **THEN** parser orchestration 不會再次對其建立重複的 `Bill` 與 `Transaction`

### Requirement: 解析成功後寫入帳單與交易資料
系統 SHALL 在 staged attachment 成功解析後，建立對應的 `Bill` 與多筆 `Transaction`，並將該附件狀態更新為 `parsed`。

#### Scenario: 成功解析後寫入資料庫
- **WHEN** 某個 staged attachment 透過某個 bank parser 成功產出 `ParseResult`
- **THEN** 系統會持久化一筆 `Bill`、多筆 `Transaction`，並將該附件標記為 `parsed`

#### Scenario: 分類尚未執行時保留原始交易資料
- **WHEN** parser orchestration 建立 `Transaction` 紀錄
- **THEN** 系統會先保存原始交易欄位（包含 `trans_date`、`posting_date`（nullable）、`merchant`、`amount` 等），而分類欄位可待後續 classifier 流程補齊

### Requirement: 所有 parser 失敗時標記為 `parse_failed`

系統 SHALL 保留既有候選規則 parser 的排序與逐一嘗試行為；當所有候選規則 parser 都無法成功解析時，SHALL 先嘗試掃描件 OCR fallback，若 OCR 仍失敗且 LLM 參考路徑已開啟，才嘗試 LLM。只有所有已啟用的解析路徑都無法產出有效帳單欄位時，才將附件標記為 `parse_failed` 並保存錯誤原因；零額歷史帳單的既有 `parse_skipped` 行為維持不變。

#### Scenario: 規則 parser 全部失敗時進入 OCR fallback

- **WHEN** 某個 staged attachment 經過所有候選規則 parser 後仍無法成功解析
- **THEN** 系統 SHALL 嘗試掃描件 OCR fallback，不得立即沿用舊的 `parse_failed` 終點

#### Scenario: 所有可用 fallback 都失敗時標記 `parse_failed`

- **WHEN** 候選規則 parser、OCR，以及（若開啟的）LLM 參考路徑都無法產出有效帳單欄位
- **THEN** 系統 SHALL 將附件標記為 `parse_failed` 並保存錯誤原因，且不得讓 pipeline 因單一附件中斷

### Requirement: Force 模式繞過 parse 去重
當 `PipelineOptions.force = True` 時，系統 SHALL 在發現已存在的 `Bill`（以 `bank_code + billing_month` 識別）後，刪除該舊 `Bill` 及其關聯的 `Transaction` 記錄，再重新執行 parser 建立新的 Bill 與 Transaction。

#### Scenario: Force 模式重新解析已存在的帳單
- **WHEN** `force = True` 且某附件解析結果的 `(bank_code, billing_month)` 已存在於 `Bill` 表
- **THEN** 系統刪除舊的 `Bill`（cascade 刪除其 `Transaction`），再建立新的 `Bill` 和 `Transaction` 記錄

#### Scenario: 非 Force 模式維持去重行為
- **WHEN** `force = False`（預設）且某帳單已存在於 `Bill` 表
- **THEN** 系統跳過該帳單的 parse，行為與變更前完全一致

#### Scenario: Force 模式下通知以新 Bill ID 觸發
- **WHEN** `force = True` 且舊 Bill 被刪除重建
- **THEN** 新 Bill 獲得新的 ID，notification 階段以新 ID 判斷是否已通知（自然去重）

### Requirement: Hybrid 路由順序為 rules → ocr →（可選）llm

系統 SHALL 依序嘗試：既有規則解析（不變的候選 parser 排序與 fallback 行為）、掃描件 OCR fallback（見 `parser-ocr`）、以及在 `BILL_PARSE_LLM_REFERENCE_ENABLED=True` 時的 LLM 參考路徑（見 `llm-reference-parsing`）。「信心足夠」統一指 `parse_confidence >= 0.85` 且 `needs_review=False`（見 `parse-result-schema`）。任一步驟成功且信心足夠 SHALL 停止後續步驟；每一步驟失敗 SHALL 落到下一步驟，而非直接中止整個 batch。

#### Scenario: 規則解析成功時不觸發 OCR 或 LLM

- **WHEN** 既有規則解析成功，`parse_confidence >= 0.85` 且 `needs_review=False`
- **THEN** 系統 SHALL 不嘗試 OCR 或 LLM 參考路徑

#### Scenario: 規則產出候選但信心不足時進入 OCR

- **WHEN** 規則 parser 產出欄位候選，但 `parse_confidence < 0.85` 或結果帶有 `needs_review=True`
- **THEN** 系統 SHALL 將規則結果保留為候選，繼續執行 OCR fallback；在 OCR 尚未產出足夠信心的結果前，不得把該規則結果視為最終結果

#### Scenario: 規則失敗、OCR 成功

- **WHEN** 規則解析失敗，且掃描件 OCR fallback 成功擷取出有效欄位、`parse_confidence >= 0.85` 且 `needs_review=False`
- **THEN** 系統 SHALL 採用 OCR 結果，`parse_method="ocr"`，且不觸發 LLM（即使 LLM 開關已開啟）

#### Scenario: OCR 產出候選但信心仍不足時才進入 LLM

- **WHEN** 規則結果失敗或信心不足，OCR 產出欄位候選但 `parse_confidence < 0.85` 或帶有 `needs_review=True`，且 `BILL_PARSE_LLM_REFERENCE_ENABLED=True`
- **THEN** 系統 SHALL 將 OCR 結果保留為候選並嘗試 LLM；LLM 輸出仍須通過 `llm-reference-parsing` 的 schema 與交叉檢查閘門

#### Scenario: 規則與 OCR 皆失敗、LLM 開啟時才嘗試 LLM

- **WHEN** 規則解析與 OCR fallback 皆失敗，且 `BILL_PARSE_LLM_REFERENCE_ENABLED=True`
- **THEN** 系統 SHALL 嘗試 LLM 參考路徑，其輸出需通過 `llm-reference-parsing` 的驗證閘門才可採用

### Requirement: 關閉所有 LLM 時，規則與 OCR 仍可獨立完成完整流程

系統 SHALL 保證在 `BILL_PARSE_LLM_REFERENCE_ENABLED=False`（或任何本機／雲端 LLM 皆不可用）的情況下，規則解析與 OCR fallback 兩步驟仍可完整跑完既有的 ingest→decrypt→parse→classify→notify 流程，不得因缺少 LLM 而使 pipeline 中斷或卡死；品質可能因此降低（更多帳單落入 `parse_failed`／`needs_review`），但流程本身必須可完成。

#### Scenario: LLM 全關時 pipeline 仍可跑完

- **WHEN** `BILL_PARSE_LLM_REFERENCE_ENABLED=False` 且批次中包含需要 OCR fallback 的掃描件
- **THEN** 整個 pipeline SHALL 正常執行到 `notify` 階段，需要人工介入的帳單以 `parse_failed`／`needs_review` 標記，而非讓整個 pipeline 失敗或掛起

#### Scenario: 驗收測試覆蓋 LLM-off 情境

- **WHEN** 執行本 capability 的驗收測試（CI 或手動）
- **THEN** SHALL 存在至少一個測試情境在 LLM 參考路徑完全關閉的前提下，驗證規則＋OCR 兩步驟可產出完整的解析結果

#### Scenario: LLM 關閉且候選仍低信心時不呼叫 LLM

- **WHEN** `BILL_PARSE_LLM_REFERENCE_ENABLED=False`，且規則／OCR 只產出 `parse_confidence=0.83` 的候選
- **THEN** 系統 SHALL 不呼叫 LLM，將結果標記 `needs_review=True` 或依既有失敗路徑標記 `parse_failed`，並 SHALL 讓 pipeline 繼續至 `notify` 階段

