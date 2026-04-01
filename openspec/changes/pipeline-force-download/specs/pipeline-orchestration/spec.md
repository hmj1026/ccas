## MODIFIED Requirements

### Requirement: 提供五階段 pipeline 的單一入口
系統 SHALL 提供一個 `run_pipeline()` 函式作為端到端帳單處理流程的單一入口，依序執行 ingest、decrypt、parse、classify、notify 五個階段。`run_pipeline()` SHALL 接受可選的 `PipelineOptions` 參數，並將其傳遞至 ingestion 和 parse 階段。

#### Scenario: Pipeline 依序執行五個階段
- **WHEN** `run_pipeline()` 被呼叫
- **THEN** 系統依序執行 ingest → decrypt → parse → classify → notify，且每個階段的輸出作為下一個階段的輸入

#### Scenario: 前一階段全部失敗時後續階段空跑
- **WHEN** 某個階段的所有項目均失敗，導致輸出為空列表
- **THEN** 後續階段以空列表輸入執行，回傳零計數，pipeline 繼續直到所有階段完成

#### Scenario: PipelineOptions 傳遞至各階段
- **WHEN** `run_pipeline(session, options=PipelineOptions(force=True, bank_code="CTBC"))` 被呼叫
- **THEN** ingestion 階段以 `force=True, bank_code="CTBC"` 執行，parse 階段以 `force=True` 執行
