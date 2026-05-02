## Why

CCAS 目前所有 pipeline 操作只能在終端機執行 `python -m ccas.pipeline ...`，對非工程使用者門檻過高，且無從在前端觀察「現在跑到哪個階段、處理了幾筆、是否失敗」。雖然 `POST /api/pipeline/trigger` 已能透過 RQ 觸發，但缺乏「執行歷史」與「進度回報」兩塊持久化資料，使用者重整頁面後無法復原狀態。本 change 補上 GUI 操作中心與 DB-backed 進度模型，使單人觀看的非工程使用者能透過瀏覽器完整掌握 pipeline 執行狀況。

## What Changes

- 新增 `frontend/src/pages/operations.tsx`，路由 `/operations`、nav 標籤「操作中心」，包含三張卡片：觸發表單、進行中進度、歷史紀錄。
- 新增 DB 表 `pipeline_runs`（透過 alembic migration），作為 pipeline 執行歷史與即時進度的單一真實來源。
- 新增 `ProgressReporter` Protocol 與兩個實作：`NoopProgressReporter`（CLI 路徑用）、`DbProgressReporter`（worker 路徑用，含 250ms 節流避免 SQLite 寫入熱點）。
- 修改 `run_pipeline()` 接受可選 `progress_reporter` 參數，每階段呼叫 `stage_started` / `stage_item_done` / `stage_finished` hook。CLI 既有 stdout JSON summary 行為不變。
- 修改 `POST /api/pipeline/trigger`：建立 `PipelineRun` row（status=queued）後再 enqueue，回應改為 `{job_id, run_id}`。
- 新增 `GET /api/pipeline/runs`（列出最近 N 筆）、`GET /api/pipeline/runs/{run_id}`（單筆詳情含階段進度）。
- 前端使用 React Query 動態輪詢：runs list 無 running 時 `staleTime: 30s`、有 running 時 `refetchInterval: 2000`；active run 詳情 `refetchInterval: 1000` 直到 status 不再是 running。
- **明確不做**：SSE / WebSocket（單人觀看場景輪詢已足夠，DB 本來就要寫，SSE 升級空間透過 `ProgressReporter` Protocol 預留，未來新增 `RedisPubsubReporter` + `CompositeProgressReporter` 即可，orchestrator 程式碼無需動）。
- **明確不做**：取消 / 重跑 已存在 run、reclassify / categories sync / staged 維護按鈕（後續 change）。
- **明確不做**：scheduler 自動觸發的 pipeline 寫入 `pipeline_runs`。scheduler 路徑刻意走 `NoopProgressReporter`（避免 scheduler 程序需共用 RQ 流程、避免 worker 不在時無法寫入），UI 「歷史紀錄」卡片頂部 SHALL 明示「僅手動觸發紀錄；scheduler 自動排程結果請查看 logs」橫幅。scheduler 寫入歷史 列為後續 enhancement。

## Capabilities

### New Capabilities
- `pipeline-operations-center`: 前端操作中心頁面 + 後端 pipeline runs 歷史 API + DB-backed 進度模型 + `ProgressReporter` 抽象層的整合 capability。涵蓋 GUI 觸發表單、進行中進度卡片、歷史表格、`pipeline_runs` 表結構、`/api/pipeline/runs*` 端點、與 worker 端的進度回報實作。

### Modified Capabilities
- `pipeline-orchestration`: `run_pipeline()` 新增可選 `progress_reporter: ProgressReporter | None` 參數，每階段須呼叫對應 hook。既有 `from_stage` / `to_stage` / `force` 等參數行為不變、CLI 路徑回傳格式不變。

## Impact

- **新檔案**：
  - `backend/alembic/versions/<ts>_add_pipeline_runs.py`
  - `backend/src/ccas/pipeline/progress.py`（Protocol + 兩個 reporter 實作）
  - `frontend/src/pages/operations.tsx` + `operations.test.tsx`
  - `frontend/e2e/operations.spec.ts`
- **修改**：
  - `backend/src/ccas/storage/models.py`（新增 `PipelineRun` 模型）
  - `backend/src/ccas/pipeline/orchestrator.py`（注入 progress_reporter）
  - `backend/src/ccas/pipeline/worker.py`（建立 PipelineRun row、傳 DbProgressReporter）
  - `backend/src/ccas/api/routers/pipeline.py`（trigger 改、新增 list/detail）
  - `backend/src/ccas/api/schemas.py`（`PipelineRunSummary`、`PipelineRunDetail`、`PipelineStageEntry`）
  - `frontend/src/App.tsx`（lazy route）、`frontend/src/components/layout.tsx`（NAV_ITEMS）、`frontend/src/lib/types.ts`
- **DB 變更**：新增 `pipeline_runs` 表、index on `(created_at desc)`、`(status)`。alembic migration 為加表、無破壞性，回滾 = drop table。
- **Runtime 依賴**：無新依賴。前端可能需 `pnpm dlx shadcn add progress badge tooltip`（如未裝）。
- **既有行為相容性**：CLI `python -m ccas.pipeline` 與 scheduler 自動觸發路徑使用 `NoopProgressReporter`，行為與 stdout 輸出格式完全不變。
- **既有 `POST /api/pipeline/trigger` API**：response shape 從 `{job_id}` 變為 `{job_id, run_id}`。屬於非破壞性擴充（前端原本就直接 dispatch，無 client 依賴 response shape；若有第三方 caller，新增欄位向後相容）。
- **後續 change 銜接**：`oauth-onboarding-ui`（拆分計畫的另一個 change）與本 change 正交，可平行進行。SSE 升級、cancel / retry 按鈕、reclassify / staged 維護等列為後續變更。
