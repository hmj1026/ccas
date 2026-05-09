# pipeline-orchestration Specification

## Purpose
TBD - created by archiving change pipeline-scheduler. Update Purpose after archive.
## Requirements
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

### Requirement: Notify 階段自主查詢未通知帳單

系統 SHALL 在 notify 階段自動查詢所有 `is_notified=False` 的帳單並發送 Telegram 通知，發送成功後標記為已通知。

#### Scenario: 新帳單自動通知
- **WHEN** parse 階段建立新的 Bill 記錄（`is_notified=False`）
- **THEN** notify 階段 SHALL 查詢到該帳單並發送 Telegram 通知

#### Scenario: 已通知帳單不重發
- **WHEN** Bill 的 `is_notified=True`
- **THEN** notify 階段 SHALL 跳過該帳單

#### Scenario: 通知成功後標記
- **WHEN** Telegram 通知發送成功
- **THEN** 系統 SHALL 將該 Bill 的 `is_notified` 設為 `True`

#### Scenario: 通知失敗不標記
- **WHEN** Telegram 通知發送失敗
- **THEN** `is_notified` SHALL 保持 `False`，下次 notify 會重試

### Requirement: 各階段部分失敗不阻斷後續處理
系統 SHALL 確保每個階段內的個別項目失敗只影響該項目本身，不中止同一階段的其他項目，也不阻斷後續階段處理已成功的項目。

#### Scenario: 單筆項目失敗後同階段其他項目繼續
- **WHEN** 某個階段處理某筆項目時發生錯誤
- **THEN** 該階段記錄該項目的錯誤，繼續處理剩餘項目，並將所有成功項目傳遞給下一階段

#### Scenario: 失敗項目不進入下一階段
- **WHEN** 某個階段有部分項目失敗
- **THEN** 只有成功的項目會被傳遞給下一個階段，失敗項目停留在當前階段並記錄失敗狀態

### Requirement: 回傳包含各階段統計的結構化 pipeline 摘要
系統 SHALL 在 `run_pipeline()` 完成後回傳結構化摘要，包含每個階段的統計數字與總耗時。摘要應包含失敗項目的詳細錯誤資訊，供 RQ job 重試邏輯與日誌記錄使用。

#### Scenario: 摘要包含所有階段的統計
- **WHEN** 一次 pipeline 完整執行完畢
- **THEN** 回傳的摘要至少包含：ingest 階段的 staged/skipped/failed 數量、decrypt 階段的 decrypted/failed 數量、parse 階段的 parsed/failed 數量、classify 階段的 classified 數量、notify 階段的 sent/failed 數量，以及從 pipeline 開始到結束的總耗時秒數、失敗清單（各失敗項目的 ID 與錯誤訊息）

#### Scenario: 階段全部略過時摘要仍完整
- **WHEN** 某個階段因無輸入項目而全部略過
- **THEN** 該階段在摘要中仍呈現，所有計數器為零

### Requirement: Pipeline 執行異常應拋出 CcasError 例外
系統 SHALL 在 pipeline 執行過程中遇到不可恢復的錯誤時拋出 `CcasError` 或其子類別。此例外應被 RQ job 層級的重試邏輯捕捉，以觸發 job 重試。

#### Scenario: Pipeline 異常被 RQ job 捕捉並重試
- **WHEN** `run_pipeline()` 拋出 `CcasError` （例如資料庫連線失敗）
- **THEN** RQ job handler 捕捉該例外，檢查重試次數是否 < 3，若是則重試；若否則標記 staging 項目為 `manual_review_needed`

### Requirement: 階段順序常數定義

系統 SHALL 定義 `STAGE_ORDER` 常數作為階段名稱與順序的唯一來源，供 `--from`/`--to` 驗證和範圍計算使用。

#### Scenario: STAGE_ORDER 包含所有五個階段

- **WHEN** 存取 `STAGE_ORDER`
- **THEN** SHALL 回傳 `("ingest", "decrypt", "parse", "classify", "notify")` 的有序 tuple

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
