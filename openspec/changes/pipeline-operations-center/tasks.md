## 1. DB 模型與 migration

- [ ] 1.1 在 `backend/src/ccas/storage/models.py` 新增 `PipelineRun` SQLAlchemy 模型（欄位依 spec D5，含 `updated_at`）
- [ ] 1.2 新增 `PipelineRunStatus` enum（queued / running / succeeded / failed / cancelled）
- [ ] 1.3 建立 alembic migration `<ts>_add_pipeline_runs.py`：建表 + `(created_at DESC)`、`(status)` 兩個索引
- [ ] 1.4 確認 downgrade 為 drop table
- [ ] 1.5 在乾淨 DB 跑 `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 驗證冪等

## 2. ProgressReporter 抽象與實作

- [ ] 2.1 建立 `backend/src/ccas/pipeline/progress.py`，定義 `ProgressReporter` Protocol 三個 async 方法
- [ ] 2.2 實作 `NoopProgressReporter`（所有方法為空）
- [ ] 2.3 實作 `DbProgressReporter`：每筆寫入用 `async_session_factory()` 開短事務、單一 UPDATE、立即 commit
- [ ] 2.4 在 `DbProgressReporter` 加入 250 ms 節流（用 `asyncio.Lock` + `last_flush_at`，同 stage 強制最後一筆 flush）
- [ ] 2.5 為 `progress.py` 寫單元測試 `test_progress_reporter.py`：覆蓋 noop、節流、強制 flush、stage_finished 即時寫、獨立短事務

## 3. Orchestrator 注入點

- [ ] 3.1 修改 `backend/src/ccas/pipeline/orchestrator.py:run_pipeline()`，新增 `progress_reporter: ProgressReporter | None = None` 參數
- [ ] 3.2 函式進入時將 None 包成 `NoopProgressReporter`
- [ ] 3.3 將 `progress_reporter` 傳入各 stage job；orchestrator 不產生假 item progress
- [ ] 3.4 階段級起訖由 stage job 或 orchestrator 統一負責，但同一 stage 不得重複呼叫 `stage_started` / `stage_finished`
- [ ] 3.5 階段內 exception 處理：在標記 failed run 或回傳 failed stage summary 前先呼叫 `stage_finished` 帶當下統計
- [ ] 3.6 明確測試 CLI / scheduler 未傳 reporter 時 stdout summary 與既有行為不變
- [ ] 3.7 新增 `test_orchestrator_progress_hook.py`：注入 fake reporter，跑短 pipeline 驗證 hook 順序與計數
- [ ] 3.8 實作前 inspect 5 個 stage job loop 點（D11），於 PR description 列出每個 hook 的 `file:line` 與 total 計算方式（特別注意 ingest 為三層 nested loop，total 計算方式須先 flatten）；確保所有 hook 點都是單純的 outer item loop、無批次 flush 干擾

## 3A. Stage job 真實進度插入點

- [ ] 3A.1 修改 `run_ingestion_job(...)` 接受可選 progress reporter / callback，在 Gmail attachments loop 內逐筆回報 processed
- [ ] 3A.2 修改 `run_decryption_job(...)` 接受可選 progress reporter / callback，在 staged attachment loop 內逐筆回報 processed
- [ ] 3A.3 修改 `run_parse_job(...)` 接受可選 progress reporter / callback，在 parse attachment loop 內逐筆回報 processed
- [ ] 3A.4 修改 `run_classify_job(...)` 接受可選 progress reporter / callback，在 transaction loop 內逐筆回報 processed
- [ ] 3A.5 修改 `run_notify_job(...)` 接受可選 progress reporter / callback，在 bills notification loop 內逐筆回報 processed
- [ ] 3A.6 為五個 stage job 增加 fake reporter 單元測試：total 正確、processed 單調遞增、空 stage 回報 total=0 且 finished
- [ ] 3A.7 確認 item-level failure 只增加 fail count / errors，不讓 processed count 卡住

## 4. Worker 整合

- [ ] 4.1 修改 `backend/src/ccas/pipeline/worker.py`，從 RQ job kwargs 取出 `run_id`
- [ ] 4.2 worker 執行開頭：將 `pipeline_runs.id=run_id` 的 status 從 queued 更新為 running、設定 `started_at`
- [ ] 4.3 建立 `DbProgressReporter(run_id)` 並傳入 `run_pipeline()`
- [ ] 4.4 執行成功：status=succeeded、設定 `completed_at`、更新 `updated_at`、確保 `stage_summary` 已完整寫入
- [ ] 4.5 修改 `on_failure_handler`：標 status=failed、寫 `error_message`、設定 `completed_at` 與 `updated_at`
- [ ] 4.6 為 worker 寫整合測試：fake redis + run 短 pipeline，驗證 status 流轉與失敗路徑
- [ ] 4.7 為 worker timeout 路徑寫測試（D9.1）：用較短 `job_timeout`（如 1s）+ stage 內 `await asyncio.sleep(2)` 模擬，驗證 RQ 觸發 `on_failure_handler` → `pipeline_runs.status` 變 `failed`、`error_message` 含 `"timeout"` 字樣（或等價辨識訊號）、`completed_at` 已設

## 5. API 端點

- [ ] 5.1 修改 `backend/src/ccas/api/routers/pipeline.py:trigger`：先建 PipelineRun(queued) row、再 enqueue 並把 run_id 帶入 job kwargs、response 改回傳 `{job_id, run_id}`
- [ ] 5.2 新增 `GET /api/pipeline/runs`：支援 `?status=`、`?limit=`（預設 20，max 100）、按 `created_at DESC` 排序
- [ ] 5.3 新增 `GET /api/pipeline/runs/{run_id}`：回完整 PipelineRunDetail；不存在回 404
- [ ] 5.4 在 `backend/src/ccas/api/schemas.py` 新增 `PipelineRunSummary`、`PipelineRunDetail`、`PipelineStageEntry`
- [ ] 5.5 新增 `test_pipeline_runs_router.py`：trigger 後 row 存在、list filter、detail shape、404 路徑
- [ ] 5.6 確認既有 `verify_token` `Depends()` 套用於新端點
- [ ] 5.7 trigger router 建立 PipelineRun row 時 `triggered_by` SHALL 寫入 `"api"` 字面值（D2.1）；不從 env / settings 讀取，由 router code 直接寫死；測試覆蓋此字面值

## 6. 前端頁面（基礎架構）

- [ ] 6.1 安裝可能缺少的 shadcn 元件：`pnpm dlx shadcn add progress badge tooltip`（如未裝）
- [ ] 6.2 在 `frontend/src/lib/types.ts` 加入 `PipelineRun`、`PipelineRunSummary`、`PipelineRunDetail`、`PipelineStageEntry` 型別
- [ ] 6.3 在 `frontend/src/App.tsx` 加 lazy route `/operations`
- [ ] 6.4 在 `frontend/src/components/layout.tsx` NAV_ITEMS 新增「操作中心」項，icon `Workflow`，插在 `/settings` 之前

## 7. 前端頁面（觸發卡片）

- [ ] 7.1 建立 `frontend/src/pages/operations.tsx` 骨架（三張卡片佔位）
- [ ] 7.2 實作觸發表單：bank select（從 `/api/settings/banks`）、year/month 兩 select、from/to_stage 兩 select、force toggle
- [ ] 7.3 client-side 驗證：from_stage <= to_stage、year/month 範圍、bank 必選或為「全部」
- [ ] 7.4 表單 submit 用 `useMutation`，成功後 `queryClient.invalidateQueries(['pipeline-runs'])`
- [ ] 7.5 提交成功後 `scrollIntoView` 到進行中卡片

## 8. 前端頁面（進行中卡片）

- [ ] 8.1 active run query：`useQuery(['pipeline-runs', runId])`、`refetchInterval: data => data?.status === 'running' ? 1000 : false`
- [ ] 8.2 階段步驟條：5 步（ingest / decrypt / parse / classify / notify），依 `current_stage` 與 `stage_summary` 渲染狀態（完成 / 進行中 / 未開始）
- [ ] 8.3 當前階段進度條：`<Progress value={processed/total*100} />` + 文字「parse 47 / 120 (39%)」
- [ ] 8.4 已過時間 client timer：從 `started_at` 起算
- [ ] 8.5 失敗時 inline banner 顯示 `error_message` 摘要與「查看詳情」連結

## 9. 前端頁面（歷史紀錄卡片）

- [ ] 9.1 runs list query：無 running 時 `staleTime: 30s`、有 running 時 `refetchInterval: 2000`
- [ ] 9.2 表格顯示：時間 / 銀行 / 期別 / 狀態 badge / 階段筆數摘要 / 耗時 / 觸發者
- [ ] 9.3 row 點擊開 Dialog 抽屜，顯示完整 `stage_summary` 表格 + `error_message`（若有）
- [ ] 9.4 status badge 顏色：succeeded 綠、failed 紅、running 藍、queued / cancelled 灰
- [ ] 9.5 卡片頂部加「僅手動觸發紀錄」橫幅（D10），附 tooltip / info icon 點擊後說明 scheduler 走 NoopProgressReporter、自動排程結果請查看 logs；橫幅樣式採 `Alert` info variant，不阻擋使用者互動

## 10. 前端測試

- [ ] 10.1 撰寫 `frontend/src/pages/operations.test.tsx`（Vitest）：表單 submit payload 正確、進行中卡片渲染、history badge 顯示
- [ ] 10.2 撰寫 `frontend/e2e/operations.spec.ts`（Playwright）：登入 → 進 `/operations` → 填表 → 提交 → 看到進行中卡片
- [ ] 10.3 確認 e2e 用 `pnpm e2e` 跑（非 `pnpm test`）

## 11. 端對端驗證

- [ ] 11.1 `bash scripts/dev-test.sh` 後端測試全綠
- [ ] 11.2 `bash scripts/dev-lint.sh` ruff + pyright 無警告
- [ ] 11.3 `pnpm test` Vitest 通過、`pnpm e2e operations.spec.ts` 通過
- [ ] 11.4 本機手動 smoke：`bash scripts/start.sh` 起 backend + frontend，登入 → `/operations` → 觸發 → 進度條跑動 → 完成 → history 出現
- [ ] 11.5 F5 重整 running run，確認進度復原（誤差不超過 1 輪詢週期）
- [ ] 11.6 故意指定無效 bank → 失敗紀錄 + error_message 顯示
- [ ] 11.7 多次連續觸發確認 RQ 串列化、UI 不會錯亂
- [ ] 11.8 worker timeout 端對端驗證：暫時將 worker `job_timeout` 改為 5s（local override），觸發一次會超時的 pipeline，驗證 PipelineRun 在約 5s 後自動標 `failed`、UI 不再顯示 running、`error_message` 有 timeout 訊號；驗證後還原 `job_timeout` 為 `30m`
- [ ] 11.9 `triggered_by` 端對端驗證：透過 API trigger 觸發、SQL 直查 `SELECT triggered_by FROM pipeline_runs ORDER BY created_at DESC LIMIT 1` 應為 `"api"`；CLI `python -m ccas.pipeline` 跑完後該指令對應的 run 不應出現在 `pipeline_runs`（CLI 走 noop）

## 12. OpenSpec 收尾

- [ ] 12.1 `openspec validate pipeline-operations-center --strict` 通過
- [ ] 12.2 與 `compose-pull-deploy` 協調合入順序（後者已 4/4，本 change 後做亦無依賴衝突）
- [ ] 12.3 完成後 `/opsx:archive pipeline-operations-center`，確認 delta 同步至 `openspec/specs/`
