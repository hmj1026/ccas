## ADDED Requirements

### Requirement: 提供五階段 pipeline 的單一入口
系統 SHALL 提供一個 `run_pipeline()` 函式作為端到端帳單處理流程的單一入口，依序執行 ingest、decrypt、parse、classify、notify 五個階段。

#### Scenario: Pipeline 依序執行五個階段
- **WHEN** `run_pipeline()` 被呼叫
- **THEN** 系統依序執行 ingest → decrypt → parse → classify → notify，且每個階段的輸出作為下一個階段的輸入

#### Scenario: 前一階段全部失敗時後續階段空跑
- **WHEN** 某個階段的所有項目均失敗，導致輸出為空列表
- **THEN** 後續階段以空列表輸入執行，回傳零計數，pipeline 繼續直到所有階段完成

### Requirement: 各階段部分失敗不阻斷後續處理
系統 SHALL 確保每個階段內的個別項目失敗只影響該項目本身，不中止同一階段的其他項目，也不阻斷後續階段處理已成功的項目。

#### Scenario: 單筆項目失敗後同階段其他項目繼續
- **WHEN** 某個階段處理某筆項目時發生錯誤
- **THEN** 該階段記錄該項目的錯誤，繼續處理剩餘項目，並將所有成功項目傳遞給下一階段

#### Scenario: 失敗項目不進入下一階段
- **WHEN** 某個階段有部分項目失敗
- **THEN** 只有成功的項目會被傳遞給下一個階段，失敗項目停留在當前階段並記錄失敗狀態

### Requirement: 回傳包含各階段統計的結構化 pipeline 摘要
系統 SHALL 在 `run_pipeline()` 完成後回傳結構化摘要，包含每個階段的統計數字與總耗時。

#### Scenario: 摘要包含所有階段的統計
- **WHEN** 一次 pipeline 完整執行完畢
- **THEN** 回傳的摘要至少包含：ingest 階段的 staged/skipped/failed 數量、decrypt 階段的 decrypted/failed 數量、parse 階段的 parsed/failed 數量、classify 階段的 classified 數量、notify 階段的 sent/failed 數量，以及從 pipeline 開始到結束的總耗時秒數

#### Scenario: 階段全部略過時摘要仍完整
- **WHEN** 某個階段因無輸入項目而全部略過
- **THEN** 該階段在摘要中仍呈現，所有計數器為零
