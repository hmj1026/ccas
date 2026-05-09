## 1. DB 模型與 migration

- [x] 1.1 在 `backend/src/ccas/storage/models.py` 新增 `PipelineRun` SQLAlchemy 模型（欄位依 spec D5，含 `updated_at`）
- [x] 1.2 新增 `PipelineRunStatus` enum（queued / running / succeeded / failed / cancelled）
- [x] 1.3 建立 alembic migration `0a2c400f1179_add_pipeline_runs.py`：建表 + `(created_at DESC)`、`(status)` 兩個索引；含 SQLite trigger 確保 Core-style bulk UPDATE 下 `updated_at` 自動刷新
- [x] 1.4 確認 downgrade 為 drop trigger + drop indexes + drop table
- [x] 1.5 在乾淨 DB 跑 `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 驗證冪等

## 2. ProgressReporter 抽象與實作

- [x] 2.1 建立 `backend/src/ccas/pipeline/progress.py`，定義 `ProgressReporter` Protocol 三個 async 方法
- [x] 2.2 實作 `NoopProgressReporter`（所有方法為空）
- [x] 2.3 實作 `DbProgressReporter`：每筆寫入用 `async_session_factory()` 開短事務、單一 UPDATE、立即 commit；引入 `AsyncSessionFactory = Callable[[], AsyncSession]` type alias 允許測試注入 instrumented factory
- [x] 2.4 在 `DbProgressReporter` 加入 250 ms 節流（用 `asyncio.Lock` + `last_flush_at`，stage_started 重置節流視窗、stage_finished 強制 flush 並覆寫 `current_stage_processed = current_stage_total`）
- [x] 2.5 為 `progress.py` 寫整合測試 `tests/integration/pipeline/test_progress_reporter.py` 9 案：noop、節流、強制 flush、stage_finished 即時寫、獨立短事務、跨 stage 重置節流、concurrent gather lock 序列化、missing run row warning fail-soft、多 stage append 順序
- [x] 2.6 擴展 `ProgressReporter.stage_finished` 契約，除 `ok` / `fail` 摘要外同步傳入 `counts` / `errors`，並串接到 `PipelineRun.stage_summary`、API schema、前端詳情 UI，避免 history 只保存 partial stage summary

## 3. Orchestrator 注入點

- [x] 3.1 修改 `backend/src/ccas/pipeline/orchestrator.py:run_pipeline()`，新增 `progress_reporter: ProgressReporter | None = None` 參數
- [x] 3.2 函式進入時將 None 包成 `NoopProgressReporter`
- [x] 3.3 階段級 hook（`stage_finished`）由 orchestrator 在 `_run_stage` 統一發出；`stage_started` / `stage_item_done` 由 §3A 的 stage job 內部 loop 自行發出（避免重複）
- [x] 3.4 同 stage 不重複呼叫 `stage_started` / `stage_finished` — orchestrator 對每階段呼叫一次 `stage_finished`，stage job 不再呼叫
- [x] 3.5 階段內 exception 處理：`_run_stage` 在 except 後仍呼叫 `stage_finished` 帶 fail=1（spec §3.5），確保 UI 不卡 running
- [x] 3.6 透過 `test_default_reporter_is_noop` 驗證 CLI / scheduler 未傳 reporter 時 Noop 包裝、五階段全跑、stdout summary 行為不變；既有 15 個 orchestrator regression test 全綠
- [x] 3.7 新增 `tests/unit/pipeline/test_orchestrator_progress_hook.py` 6 案：default Noop、stage_finished 每階段一次、ok/fail split、exception path 仍發 finished、elapsed_ms 非負、stage range subset
- [x] 3.8 實作前 inspect 5 個 stage job loop 點（已記錄於 design.md D11）：ingest 三層 nested loop（`ingestor/job.py:404-430`，total 為全部 attachment flatten 總數，pre-flatten 計算）；decrypt/parse/classify/notify 皆為單層 outer item loop。實際 §3A 實作在 Commit 4。

## 3A. Stage job 真實進度插入點

- [x] 3A.1 修改 `run_ingestion_job(...)` 接受可選 progress reporter，per-bank Gmail 搜尋完成後 emit `stage_started` with bank-local total（pre-flatten attachments + html fallback），最內層 attachment loop 逐筆回報 processed（bank-local counter）
- [x] 3A.2 修改 `run_decryption_job(...)` 接受可選 progress reporter，loop 之前 emit `stage_started(total=len(attachments))`，inner try/finally 內逐筆回報 processed
- [x] 3A.3 修改 `run_parse_job(...)` 接受可選 progress reporter，loop 之前 emit `stage_started(total=len(attachments))`，inner try/finally 內逐筆回報 processed
- [x] 3A.4 修改 `run_classify_job(...)` 接受可選 progress reporter，loop 之前 emit `stage_started(total=len(transactions))`，inner try/finally 內逐筆回報 processed
- [x] 3A.5 修改 `run_notify_job(...)` 接受可選 progress reporter，loop 之前 emit `stage_started(total=len(bill_rows))`，inner try/finally 內逐筆回報 processed；Telegram 未設定或無未通知帳單時 emit `stage_started(total=0)` 即返回
- [x] 3A.6 新增 `tests/unit/pipeline/test_stage_progress_hooks.py` 11 案：classify monotonic / empty / item failure；decrypt full+empty；parse full；notify full+disabled；ingest per-bank reset / no banks / item failure advances processed
- [x] 3A.7 item-level failure 在 inner `finally` 內 `processed += 1`，與 success counter 分離；測試覆蓋 classify 與 ingest 兩處（spec §3A.7）

## 4. Worker 整合

- [x] 4.1 修改 `backend/src/ccas/pipeline/worker.py`，從 RQ job kwargs 取出 `run_id`
- [x] 4.2 worker 執行開頭：將 `pipeline_runs.id=run_id` 的 status 從 queued 更新為 running、設定 `started_at`
- [x] 4.3 建立 `DbProgressReporter(run_id)` 並傳入 `run_pipeline()`
- [x] 4.4 執行成功：status=succeeded、設定 `completed_at`、更新 `updated_at`、確保 `stage_summary` 已完整寫入
- [x] 4.5 修改 `on_failure_handler`：標 status=failed、寫 `error_message`、設定 `completed_at` 與 `updated_at`
- [x] 4.6 為 worker 寫整合測試：fake redis + run 短 pipeline，驗證 status 流轉與失敗路徑
- [x] 4.7 為 worker timeout 路徑寫測試（D9.1）：用較短 `job_timeout`（如 1s）+ stage 內 `await asyncio.sleep(2)` 模擬，驗證 RQ 觸發 `on_failure_handler` → `pipeline_runs.status` 變 `failed`、`error_message` 含 `"timeout"` 字樣（或等價辨識訊號）、`completed_at` 已設

## 5. API 端點

- [x] 5.1 修改 `backend/src/ccas/api/routers/pipeline.py:trigger`：先建 PipelineRun(queued) row、再 enqueue 並把 run_id 帶入 job kwargs、response 改回傳 `{job_id, run_id}`
- [x] 5.2 新增 `GET /api/pipeline/runs`：支援 `?status=`、`?limit=`（預設 20，max 100）、按 `created_at DESC` 排序
- [x] 5.3 新增 `GET /api/pipeline/runs/{run_id}`：回完整 PipelineRunDetail；不存在回 404
- [x] 5.4 在 `backend/src/ccas/api/schemas.py` 新增 `PipelineRunSummary`、`PipelineRunDetail`、`PipelineStageEntry`
- [x] 5.5 新增 `test_pipeline_runs_router.py`：trigger 後 row 存在、list filter、detail shape、404 路徑
- [x] 5.6 確認既有 `verify_token` `Depends()` 套用於新端點
- [x] 5.7 trigger router 建立 PipelineRun row 時 `triggered_by` SHALL 寫入 `"api"` 字面值（D2.1）；不從 env / settings 讀取，由 router code 直接寫死；測試覆蓋此字面值

## 6. 前端頁面（基礎架構）

- [x] 6.1 安裝可能缺少的 shadcn 元件：`pnpm dlx shadcn add progress badge tooltip`（如未裝）
- [x] 6.2 在 `frontend/src/lib/types.ts` 加入 `PipelineRun`、`PipelineRunSummary`、`PipelineRunDetail`、`PipelineStageEntry` 型別
- [x] 6.3 在 `frontend/src/App.tsx` 加 lazy route `/operations`
- [x] 6.4 在 `frontend/src/components/layout.tsx` NAV_ITEMS 新增「操作中心」項，icon `Workflow`，插在 `/settings` 之前

## 7. 前端頁面（觸發卡片）

- [x] 7.1 建立 `frontend/src/pages/operations.tsx` 骨架（三張卡片佔位）
- [x] 7.2 實作觸發表單：bank select（從 `/api/settings/banks`）、year/month 兩 select、from/to_stage 兩 select、force toggle
- [x] 7.3 client-side 驗證：from_stage <= to_stage、year/month 範圍、bank 必選或為「全部」
- [x] 7.4 表單 submit 用 `useMutation`，成功後 `queryClient.invalidateQueries(['pipeline-runs'])`
- [x] 7.5 提交成功後 `scrollIntoView` 到進行中卡片

## 8. 前端頁面（進行中卡片）

- [x] 8.1 active run query：`useQuery(['pipeline-runs', runId])`、`refetchInterval: data => data?.status === 'running' ? 1000 : false`
- [x] 8.2 階段步驟條：5 步（ingest / decrypt / parse / classify / notify），依 `current_stage` 與 `stage_summary` 渲染狀態（完成 / 進行中 / 未開始）
- [x] 8.3 當前階段進度條：`<Progress value={processed/total*100} />` + 文字「parse 47 / 120 (39%)」
- [x] 8.4 已過時間 client timer：從 `started_at` 起算
- [x] 8.5 失敗時 inline banner 顯示 `error_message` 摘要與「查看詳情」連結

## 9. 前端頁面（歷史紀錄卡片）

- [x] 9.1 runs list query：無 running 時 `staleTime: 30s`、有 running 時 `refetchInterval: 2000`
- [x] 9.2 表格顯示：時間 / 銀行 / 期別 / 狀態 badge / 階段筆數摘要 / 耗時 / 觸發者
- [x] 9.3 row 點擊開 Dialog 抽屜，顯示完整 `stage_summary` 表格 + `error_message`（若有）
- [x] 9.4 status badge 顏色：succeeded 綠、failed 紅、running 藍、queued / cancelled 灰
- [x] 9.5 卡片頂部加「僅手動觸發紀錄」橫幅（D10），附 tooltip / info icon 點擊後說明 scheduler 走 NoopProgressReporter、自動排程結果請查看 logs；橫幅樣式採 `Alert` info variant，不阻擋使用者互動

## 10. 前端測試

- [x] 10.1 撰寫 `frontend/src/pages/operations.test.tsx`（Vitest）：表單 submit payload 正確、進行中卡片渲染、history badge 顯示
- [x] 10.2 撰寫 `frontend/e2e/operations.spec.ts`（Playwright）：登入 → 進 `/operations` → 填表 → 提交 → 看到進行中卡片
- [x] 10.3 確認 e2e 用 `pnpm e2e` 跑（非 `pnpm test`）

## 11. 端對端驗證

- [x] 11.1 `bash scripts/dev-test.sh` 後端測試全綠
- [x] 11.2 `bash scripts/dev-lint.sh` ruff + pyright 無警告
- [x] 11.3 `pnpm test` Vitest 通過、`pnpm e2e operations.spec.ts` 通過
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
