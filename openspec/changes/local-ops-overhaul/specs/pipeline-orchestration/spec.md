## MODIFIED Requirements

### Requirement: 提供五階段 pipeline 的單一入口
系統 SHALL 提供一個 `run_pipeline()` 函式作為端到端帳單處理流程的單一入口，依序執行 ingest、decrypt、parse、classify、notify 五個階段。`run_pipeline()` SHALL 接受可選的 `PipelineOptions` 參數，並將其傳遞至各階段。當 `PipelineOptions` 包含 `from_stage` 或 `to_stage` 時，SHALL 只執行指定範圍內的階段。

#### Scenario: Pipeline 依序執行五個階段
- **WHEN** `run_pipeline()` 被呼叫且未指定 `from_stage`/`to_stage`
- **THEN** 系統依序執行 ingest → decrypt → parse → classify → notify，且每個階段的輸出作為下一個階段的輸入

#### Scenario: 前一階段全部失敗時後續階段空跑
- **WHEN** 某個階段的所有項目均失敗，導致輸出為空列表
- **THEN** 後續階段以空列表輸入執行，回傳零計數，pipeline 繼續直到所有階段完成

#### Scenario: PipelineOptions 傳遞至各階段
- **WHEN** `run_pipeline(session, options=PipelineOptions(force=True, bank_code="CTBC"))` 被呼叫
- **THEN** ingestion 階段以 `force=True, bank_code="CTBC"` 執行，parse 階段以 `force=True` 執行

#### Scenario: 使用 --from 從指定階段開始
- **WHEN** `run_pipeline(session, options=PipelineOptions(from_stage="decrypt"))` 被呼叫
- **THEN** 系統 SHALL 跳過 ingest，從 decrypt 開始依序執行 decrypt → parse → classify → notify

#### Scenario: 使用 --to 執行到指定階段停止
- **WHEN** `run_pipeline(session, options=PipelineOptions(to_stage="parse"))` 被呼叫
- **THEN** 系統 SHALL 依序執行 ingest → decrypt → parse，不執行 classify 和 notify

#### Scenario: 使用 --from 和 --to 組合指定範圍
- **WHEN** `run_pipeline(session, options=PipelineOptions(from_stage="decrypt", to_stage="classify"))` 被呼叫
- **THEN** 系統 SHALL 只執行 decrypt → parse → classify

#### Scenario: --from 和 --to 指定同一階段
- **WHEN** `run_pipeline(session, options=PipelineOptions(from_stage="parse", to_stage="parse"))` 被呼叫
- **THEN** 系統 SHALL 只執行 parse 階段

#### Scenario: 無效階段名稱
- **WHEN** `from_stage` 或 `to_stage` 指定了不存在的階段名稱
- **THEN** 系統 SHALL 拋出 `ValueError`，訊息中包含有效的階段名稱列表

#### Scenario: from_stage 在 to_stage 之後
- **WHEN** `from_stage="classify"` 且 `to_stage="decrypt"`
- **THEN** 系統 SHALL 拋出 `ValueError`，提示 from_stage 必須在 to_stage 之前或相同

## ADDED Requirements

### Requirement: 階段順序常數定義

系統 SHALL 定義 `STAGE_ORDER` 常數作為階段名稱與順序的唯一來源，供 `--from`/`--to` 驗證和範圍計算使用。

#### Scenario: STAGE_ORDER 包含所有五個階段

- **WHEN** 存取 `STAGE_ORDER`
- **THEN** SHALL 回傳 `("ingest", "decrypt", "parse", "classify", "notify")` 的有序 tuple
