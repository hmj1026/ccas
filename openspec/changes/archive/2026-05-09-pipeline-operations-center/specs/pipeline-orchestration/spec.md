## ADDED Requirements

### Requirement: run_pipeline 接受 progress_reporter 參數

`run_pipeline()` SHALL 新增可選關鍵字參數 `progress_reporter: ProgressReporter | None = None`。當該參數為 `None` 時，系統 SHALL 內部包成 `NoopProgressReporter`，所有階段 hook 為空操作、不影響既有行為。當該參數為 `ProgressReporter` 實例時，每階段開頭 SHALL 呼叫 `await progress_reporter.stage_started(stage, total)`、每處理完一筆 SHALL 呼叫 `await progress_reporter.stage_item_done(stage, processed)`、階段結束 SHALL 呼叫 `await progress_reporter.stage_finished(stage, ok, fail, elapsed_ms, counts=counts, errors=errors)`。`ok` / `fail` 為摘要欄位；`counts` / `errors` SHALL 來自該階段的 `StageSummary`，供 `PipelineRun.stage_summary` 保存完整快照。

#### Scenario: CLI 路徑使用 noop

- **WHEN** CLI 執行 `python -m ccas.pipeline run`，未傳 `progress_reporter`
- **THEN** `run_pipeline()` SHALL 使用 `NoopProgressReporter`，stdout JSON summary 輸出格式與本 change 前完全一致

#### Scenario: scheduler 路徑使用 noop

- **WHEN** APScheduler 觸發 `run_pipeline()`，未傳 `progress_reporter`
- **THEN** 行為與 CLI 一致，不對 `pipeline_runs` 表產生任何寫入

#### Scenario: worker 路徑注入 DbProgressReporter

- **WHEN** RQ worker 執行 pipeline job，傳入 `DbProgressReporter(run_id=X)`
- **THEN** `run_pipeline()` SHALL 在每階段開頭、每筆處理完、階段結束分別呼叫對應 hook，DB 中 `pipeline_runs.id=X` 的 row 進度欄位 SHALL 隨執行進度更新

#### Scenario: hook 呼叫順序正確

- **WHEN** `run_pipeline()` 執行 ingest 階段，處理 5 筆資料
- **THEN** hook 呼叫順序 SHALL 為：`stage_started("ingest", total=5)` → 5 次 `stage_item_done("ingest", processed=N)` → `stage_finished("ingest", ok, fail, elapsed_ms, counts=..., errors=...)`，下一階段開始前 SHALL 已完成本階段所有 hook

#### Scenario: 階段範圍限制下 hook 仍正確

- **WHEN** `run_pipeline(progress_reporter=R, options=PipelineOptions(from_stage="parse", to_stage="classify"))` 執行
- **THEN** R SHALL 僅收到 parse 與 classify 兩階段的 started / item_done / finished hook，ingest / decrypt / notify 階段 SHALL 不觸發任何 hook 呼叫

#### Scenario: 階段內 exception 仍呼叫 stage_finished

- **WHEN** parse 階段在處理第 50 筆時 raise exception
- **THEN** 系統 SHALL 在標記該 run 失敗或回傳 failed stage summary 前呼叫 `stage_finished("parse", ok=49, fail=1, elapsed_ms=..., counts=..., errors=...)`，避免 DB 中 `current_stage` 永久卡住；CLI stdout contract 不得因 GUI progress hook 無意改變

### Requirement: stage job item loop 提供真實進度來源

若 UI 顯示 `current_stage_processed / current_stage_total`，系統 SHALL 從各 stage job 的實際 item loop 回報進度，不得由 orchestrator 產生假進度。`run_ingestion_job`、`run_decryption_job`、`run_parse_job`、`run_classify_job`、`run_notify_job` SHALL 接受可選 progress reporter 或等價 callback。每個 stage job SHALL 在查得待處理 item 總數後回報 total，並於每筆 item 完成後回報 processed count。

#### Scenario: parse 階段逐筆回報

- **WHEN** parse job 查得 120 筆待解析 attachment
- **THEN** parse job SHALL 呼叫 `stage_started("parse", total=120)`，並在每筆 attachment 完成 parsed / skipped / failed 狀態處理後呼叫 `stage_item_done("parse", processed=N)`

#### Scenario: classify 階段逐筆回報

- **WHEN** classify job 查得 50 筆待分類交易
- **THEN** classify job SHALL 呼叫 `stage_started("classify", total=50)`，並在每筆 transaction 完成分類或跳過後呼叫 `stage_item_done("classify", processed=N)`

#### Scenario: 空 stage 仍回報完整狀態

- **WHEN** notify stage 沒有任何待通知帳單
- **THEN** notify job SHALL 回報 `stage_started("notify", total=0)` 與 `stage_finished("notify", ok=0, fail=0, elapsed_ms=..., counts=..., errors=...)`，UI SHALL 顯示該 stage 已完成而非 stuck
