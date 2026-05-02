## ADDED Requirements

### Requirement: Pipeline 執行歷史 DB 模型

系統 SHALL 提供 `pipeline_runs` 資料表作為 pipeline 執行歷史與即時進度的單一真實來源。每筆 pipeline 觸發 SHALL 對應一筆 `PipelineRun` row，欄位至少包含：`id`（UUID PK）、`job_id`（RQ id）、`status`（queued / running / succeeded / failed / cancelled）、`triggered_by`、`params`（JSON：force / bank_code / year / month / from_stage / to_stage）、`current_stage`、`current_stage_processed`、`current_stage_total`、`stage_summary`（JSON 陣列：每階段 ok / fail / elapsed_ms）、`error_message`、`started_at`、`completed_at`、`created_at`、`updated_at`。資料表 SHALL 含 `(created_at DESC)` 與 `(status)` 兩個索引。

#### Scenario: trigger 立即建立 row

- **WHEN** 使用者透過前端觸發 pipeline
- **THEN** 系統 SHALL 在 enqueue RQ job 之前先在 `pipeline_runs` 表建立一筆 status=queued 的 row，並回傳 `run_id`

#### Scenario: 每次進度寫入更新 updated_at

- **WHEN** `DbProgressReporter` 寫入 current_stage 或 stage_summary
- **THEN** `pipeline_runs.updated_at` SHALL 同步更新為目前時間，供 UI 顯示最後更新時間與未來 stale detection 使用

#### Scenario: 資料表索引支援 list 查詢

- **WHEN** 後端執行 `SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT 20`
- **THEN** 查詢 SHALL 命中 `(created_at DESC)` 索引、響應時間 SHALL 在 100 ms 以下（資料量 10K 以下）

#### Scenario: triggered_by 在 API 與 CLI 路徑寫入正確字面值

- **WHEN** `POST /api/pipeline/trigger` 建立 PipelineRun row
- **THEN** `triggered_by` SHALL 寫入 `"api"` 字面值；CLI 路徑（`python -m ccas.pipeline`）走 NoopProgressReporter 不寫 PipelineRun，scheduler 路徑亦同（見 D10），`triggered_by` 字面值 SHALL 由各 caller 端寫死，不從 env 讀取

#### Scenario: alembic migration 為加表且可回滾

- **WHEN** 執行 `alembic upgrade head`
- **THEN** 系統 SHALL 建立 `pipeline_runs` 表與相關索引，不修改任何既有表結構；`alembic downgrade -1` SHALL 為 drop table 操作、回滾後既有資料完整保留

### Requirement: ProgressReporter 抽象層

系統 SHALL 提供 `ProgressReporter` Protocol 並至少實作兩個版本：`NoopProgressReporter`（CLI / scheduler 路徑用，所有 hook 為空操作）、`DbProgressReporter`（worker 路徑用，將進度寫入 `pipeline_runs` 對應 row）。Protocol 介面 SHALL 包含三個 async 方法：`stage_started(stage, total)`、`stage_item_done(stage, processed)`、`stage_finished(stage, ok, fail, elapsed_ms)`。

#### Scenario: NoopProgressReporter 不寫 DB

- **WHEN** CLI 路徑呼叫 `run_pipeline()` 不傳 `progress_reporter`
- **THEN** 系統 SHALL 內部包成 `NoopProgressReporter`，所有 hook 呼叫 SHALL 為空操作、不對 DB 產生任何寫入

#### Scenario: DbProgressReporter 寫入對應欄位

- **WHEN** worker 執行 pipeline 並使用 `DbProgressReporter(run_id=X)`
- **THEN** `stage_started("parse", total=120)` 呼叫 SHALL 將 `pipeline_runs.id=X` 的 `current_stage` 更新為 `"parse"`、`current_stage_total` 為 `120`、`current_stage_processed` 為 `0`

#### Scenario: stage_item_done 節流

- **WHEN** classify 階段一秒內呼叫 `stage_item_done` 50 次
- **THEN** `DbProgressReporter` SHALL 對同階段的 `stage_item_done` 呼叫進行 250 ms 節流，實際寫入 DB 次數 SHALL 不超過 5 次/秒；該階段最後一筆 SHALL 強制 flush

#### Scenario: stage_finished 即時寫入

- **WHEN** parse 階段結束呼叫 `stage_finished("parse", ok=120, fail=0, elapsed_ms=8200)`
- **THEN** `DbProgressReporter` SHALL 立即寫入：將 `stage_summary` JSON 陣列追加 `{stage: "parse", ok: 120, fail: 0, elapsed_ms: 8200}`、覆寫 `current_stage_processed = current_stage_total`，不受節流限制

#### Scenario: 每筆寫入使用獨立短事務

- **WHEN** `DbProgressReporter` 任一 hook 觸發寫入
- **THEN** 系統 SHALL 為該寫入開啟獨立 async session、執行單一 UPDATE、立即 commit；不得持有跨 hook 的長活 session

#### Scenario: worker crash 時標 failed

- **WHEN** worker 在 pipeline 執行中 raise exception
- **THEN** RQ on_failure handler SHALL 將 `pipeline_runs.status` 設為 `failed`、寫入 `error_message`、設定 `completed_at`

#### Scenario: worker job timeout 時標 failed 而非永久 running

- **WHEN** worker 執行的 pipeline 超過 RQ `job_timeout`（30m）
- **THEN** RQ SHALL 觸發 `on_failure_handler` 將 `pipeline_runs.status` 設為 `failed`、`error_message` 寫入含 `"job timeout"` 字樣（或等價描述讓使用者辨識超時 vs 一般 crash）、設 `completed_at`；status SHALL 不得永久卡 `running` 狀態

### Requirement: Pipeline Runs 列表與詳情 API

系統 SHALL 提供 `GET /api/pipeline/runs` 列出最近 N 筆執行紀錄（預設 N=20，max 100），與 `GET /api/pipeline/runs/{run_id}` 回傳單筆詳情含階段進度與 stage_summary。`/api/pipeline/runs` SHALL 支援 `?status=` 與 `?limit=` query parameters。`POST /api/pipeline/trigger` 的 response shape SHALL 從 `{job_id}` 擴充為 `{job_id, run_id}`，先建立 PipelineRun row 再 enqueue 以避免 race。

#### Scenario: 列表預設回傳最近 20 筆

- **WHEN** 前端呼叫 `GET /api/pipeline/runs`
- **THEN** 系統 SHALL 回傳最近 20 筆 PipelineRunSummary，按 `created_at DESC` 排序

#### Scenario: 列表支援 status filter

- **WHEN** 前端呼叫 `GET /api/pipeline/runs?status=failed&limit=50`
- **THEN** 系統 SHALL 僅回傳 status=failed 的紀錄、最多 50 筆

#### Scenario: 詳情含完整 stage_summary

- **WHEN** 前端呼叫 `GET /api/pipeline/runs/{run_id}`，run 已執行完前 3 個階段
- **THEN** response SHALL 包含 `stage_summary`（已完成 3 階段的 ok / fail / elapsed_ms 陣列）、`current_stage`（第 4 階段）、`current_stage_processed`、`current_stage_total`、`params`、`triggered_by`、所有時間戳

#### Scenario: trigger 回應含 run_id

- **WHEN** 前端呼叫 `POST /api/pipeline/trigger` 帶有效參數
- **THEN** 系統 SHALL 在 DB 建立 PipelineRun(status=queued) row、enqueue RQ job 帶入 run_id、回應 `{job_id, run_id}` 兩個欄位

#### Scenario: trigger 後 list 立即可見

- **WHEN** 前端 trigger 成功 → 立刻呼叫 `GET /api/pipeline/runs`
- **THEN** 該筆新 run SHALL 出現在列表第一筆、status=queued 或 running

#### Scenario: 不存在的 run_id 回 404

- **WHEN** 前端呼叫 `GET /api/pipeline/runs/{not_exist_id}`
- **THEN** 系統 SHALL 回應 HTTP 404、訊息指出 run not found

### Requirement: 操作中心前端頁面

系統 SHALL 提供 `/operations` 路由，nav 標籤「操作中心」、icon 為 lucide `Workflow`，插在 `/settings` 之前。頁面 SHALL 由三張卡片組成：(1) **觸發卡片**含表單（銀行 select、年月、起訖階段、強制重跑 toggle、開始執行按鈕）、(2) **進行中卡片**僅當有 running run 時顯示，含階段步驟條（5 步狀態：完成 / 進行中 / 未開始）、當前階段進度條與 `已處理 / 總數` 文字、(3) **歷史紀錄卡片**含表格（時間 / 銀行 / 期別 / 狀態 badge / 階段筆數摘要 / 耗時 / 觸發者）與展開抽屜檢視完整 stage_summary 與 error_message。

#### Scenario: 觸發成功捲動到進行中卡片

- **WHEN** 使用者填表後點「開始執行」、API 回應成功
- **THEN** 頁面 SHALL 自動捲動到進行中卡片、顯示 status=queued 或 running 的 run

#### Scenario: 進行中卡片正確顯示階段進度

- **WHEN** 後端回傳 `current_stage="parse"`、`current_stage_processed=47`、`current_stage_total=120`
- **THEN** 進行中卡片 SHALL 顯示「parse 47 / 120 (39%)」、第 3 步（parse）顯示 spinner、前 2 步顯示綠勾、後 2 步顯示灰圓

#### Scenario: F5 重整 running run 復原

- **WHEN** 使用者在 pipeline 跑到 parse 階段時 F5 重整
- **THEN** 頁面 SHALL 透過 `GET /api/pipeline/runs/{id}` 復原進度顯示，與重整前狀態一致（誤差不超過一個輪詢週期）

#### Scenario: 歷史紀錄展開查看詳情

- **WHEN** 使用者點擊歷史表格中的某一 row
- **THEN** 系統 SHALL 開啟 Dialog 抽屜、顯示完整 `stage_summary` 與 `error_message`（若有）

#### Scenario: 表單客戶端驗證

- **WHEN** 使用者選擇 from_stage="classify"、to_stage="parse"（順序錯誤）
- **THEN** 系統 SHALL 在客戶端阻擋送出、顯示錯誤訊息「from_stage 必須在 to_stage 之前或相同」

#### Scenario: 歷史紀錄卡片揭露 scheduler 走 noop

- **WHEN** 使用者進入 `/operations` 頁面、檢視歷史紀錄卡片
- **THEN** 卡片頂部 SHALL 顯示橫幅「僅手動觸發紀錄；scheduler 自動排程結果請查看 logs」並附 tooltip 說明 scheduler 路徑刻意走 NoopProgressReporter（見設計 D10），避免使用者誤以為「設了排程但歷史看不到 → 排程沒跑」

### Requirement: 前端動態輪詢策略

前端 SHALL 透過 React Query 實作分層輪詢：runs list query 在無 running run 時 `staleTime: 30s` 不主動拉、有 running run 時 `refetchInterval: 2000`；active run detail query 使用 `refetchInterval: (data) => data?.status === 'running' ? 1000 : false`，run 完成後自動停止。系統 SHALL **不**使用 SSE / WebSocket。

#### Scenario: 無 running 時不主動輪詢

- **WHEN** 頁面載入、最近 20 筆全為 succeeded / failed
- **THEN** runs list query SHALL 在 30 秒內不重複拉取（除非 user 手動 invalidate）

#### Scenario: 有 running 時 list 每 2 秒拉一次

- **WHEN** runs list 中存在至少一筆 status=running 的 run
- **THEN** list query SHALL 每 2 秒重新拉取，直到所有 run 不再為 running

#### Scenario: active run 完成後停止輪詢

- **WHEN** active run detail 收到 status=succeeded
- **THEN** detail query SHALL 立即停止 `refetchInterval`、不再主動拉取

#### Scenario: 視窗失焦不浪費輪詢

- **WHEN** 使用者切到其他瀏覽器分頁
- **THEN** React Query SHALL 暫停 `refetchInterval`、切回後立即 refetch 一次

### Requirement: ProgressReporter 升級空間預留

系統設計 SHALL 確保未來加入 SSE / WebSocket 等 server push 機制時，僅需新增 `RedisPubsubReporter` 與 `CompositeProgressReporter([Db, Pubsub])`，**不得**修改 `run_pipeline()` 函式介面、`orchestrator.py` 階段 hook 呼叫位置、worker enqueue 邏輯。`GET /api/pipeline/runs/{id}` response shape SHALL 為完整快照（含 current_stage、stage_summary、所有時間戳），未來若改 SSE 推送，payload 結構 SHALL 不變。

#### Scenario: 介面穩定性檢查

- **WHEN** 比對本 change 落地後的 `ProgressReporter` Protocol 與 `run_pipeline()` 簽章
- **THEN** 未來新增 SSE 時 SHALL 不需修改本 change 定義的 Protocol 方法名稱、參數、回傳型別

#### Scenario: API response 為完整快照

- **WHEN** 前端呼叫 `GET /api/pipeline/runs/{id}`
- **THEN** response SHALL 包含足夠資訊讓前端在無歷史 state 的前提下完整重建畫面（不依賴 incremental updates）
