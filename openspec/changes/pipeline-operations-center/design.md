## Context

CCAS pipeline 由五階段（ingest → decrypt → parse → classify → notify）構成，由 `backend/src/ccas/pipeline/orchestrator.py:run_pipeline()` 統一驅動。觸發路徑有三：CLI（`python -m ccas.pipeline`）、scheduler（APScheduler 定時）、HTTP API（`POST /api/pipeline/trigger` → RQ 排入 worker）。當前痛點：

1. **狀態盲區**：trigger 後使用者只拿到 `job_id`，看不到階段進度、無法判斷「是還在跑、還是已經 stuck」。
2. **歷史空白**：跑完即遺，不知道過去 7 天執行幾次、哪幾次失敗。
3. **重整即失憶**：即使加了即時推播，重整頁面也無法復原 — 沒有 SSOT。
4. **CLI 單一入口**：非工程同事無法獨立執行，必須請工程同事代跑。

設計約束：
- 本專案使用 SQLite + WAL，**單寫多讀**模式不適合高頻寫入。進度回報必須節流。
- RQ worker 是獨立 process，不共享 FastAPI 的 SSE 連線池。任何 server push 設計必須跨 process。
- 單人觀看：本服務只有少數使用者，不會多人同時盯同一個 run。
- 既有 CLI / scheduler 路徑必須完全不受影響。

## Goals / Non-Goals

**Goals:**
- 使用者透過 `/operations` 頁面可一鍵觸發 pipeline，看到階段步驟條（5 步）+ 當前階段 `已處理 / 總數` 進度條。
- 重整頁面後 running run 仍能完整復原（progress、started_at、stage_summary）。
- 列出最近 20 次執行歷史，可展開查看每次階段筆數、耗時、失敗原因。
- CLI 與 scheduler 路徑完全不變，不引入 RQ 之外的耦合。
- 預留 SSE 升級空間：未來加入 SSE 不需動 orchestrator 與 worker 程式碼。

**Non-Goals:**
- SSE / WebSocket 即時推播（升級空間預留，本次不實作）。
- 取消 / 重跑 已建立的 run（cancel endpoint 與 UI 按鈕，列為 Phase 2）。
- Reclassify / categories sync / staged 維護等其他 pipeline 操作按鈕（範疇收斂）。
- 操作審計（誰在何時跑了什麼）— `triggered_by` 欄位已預留，UI filter 列後續 enhancement。
- 多 run 並發控制 — RQ default queue 已串列化 worker，本 change 假設同一時間至多一個 running run（若強行並發，UI 會選最近一筆顯示，DB 不會錯誤）。

## Decisions

### D1：進度回報走 DB-backed + 動態輪詢，不上 SSE

選擇：新增 `pipeline_runs` 表存進度欄位（`current_stage`、`current_stage_processed`、`current_stage_total`、`stage_summary`），前端用 React Query `refetchInterval` 主動拉。

替代方案：
- **SSE / WebSocket**：被否決。RQ worker 與 FastAPI 是不同 process，server push 需在中間架 Redis pubsub bridge、處理 reconnect / heartbeat / last-event-id replay。**收益小**（單人觀看，扇出 = 1）、**成本大**（多一條 transport、多一份故障模式）。DB 本來就要寫（為了重整復原），SSE 不替代這次寫入，只是疊加。
- **記憶體狀態 + WS**：被否決，重整即失憶，違反目標。
- **Redis-only state**：被否決，無法支援歷史查詢。

理由：DB 是 SSOT，輪詢是最簡單的查詢方式。1 秒延遲對人眼與「pipeline 跑數十秒到 30 分鐘」的時長尺度不可感知。

**升級空間**：`ProgressReporter` 是 Protocol，未來新增 `RedisPubsubReporter` 廣播事件 + `CompositeProgressReporter([Db, Pubsub])`，orchestrator 注入點不動。前端 `GET /runs/{id}` 設計為完整快照，未來換成 SSE 也是同樣的 payload，hook 替換無痛。

### D2：`ProgressReporter` Protocol + 注入式

選擇：

```python
class ProgressReporter(Protocol):
    async def stage_started(self, stage: str, total: int) -> None: ...
    async def stage_item_done(self, stage: str, processed: int) -> None: ...
    async def stage_finished(self, stage: str, ok: int, fail: int, elapsed_ms: int) -> None: ...
```

`run_pipeline(session, options=..., progress_reporter=None)`，預設 None → 內部包成 `NoopProgressReporter`。CLI / scheduler 路徑不傳 → noop，行為不變。RQ worker 在 enqueue 時傳 `DbProgressReporter(run_id)`。因現有 orchestrator 只在 stage job 完成後收到 summary，若要支援「已處理 / 總數」的即時進度，progress_reporter 必須由 orchestrator 繼續傳入各 stage job，stage job 在自己的 item loop 內呼叫 `stage_item_done`。

替代方案：
- **callback 函式對**：被否決，三個 hook 用三個 callback 介面散亂。Protocol 集中、易測試。
- **events bus**（pub/sub 風格）：被否決，當前只有 1 個 consumer（DB），過度工程。

**附帶決策（D2.1）：`triggered_by` 欄位字面值來源**

| 觸發路徑 | `triggered_by` 寫入值 | 寫入位置 |
|---|---|---|
| `POST /api/pipeline/trigger`（前端 / API caller） | `"api"` | router 建立 PipelineRun row 時 |
| `python -m ccas.pipeline`（CLI） | `"cli"` | 不適用（CLI 走 NoopProgressReporter，不寫 PipelineRun） |
| APScheduler 自動觸發 | 不適用 | 走 NoopProgressReporter（見 D10），不寫 PipelineRun |
| 未來 SSE / OAuth callback / Telegram bot 觸發 | 擴增字面值（`"sse"` / `"oauth"` / `"telegram"`） | 各 caller 端 |

理由：欄位設計支援未來 audit / filter，但本 change 僅前端 API trigger 走 `"api"`；不在 `Settings` 暴露這個值（避免 env 漂移），由 router code 直接寫死。

### D3：寫入節流 250 ms

選擇：`DbProgressReporter.stage_item_done` 對同一 stage 的高頻呼叫加 250 ms 節流（同階段最後一筆強制 flush，避免漏掉 99/100 顯示）。`stage_started` 與 `stage_finished` 一定即時寫。

替代方案：
- **不節流**：被否決。classify 階段一秒可處理數十筆，每筆獨立短事務 → SQLite 寫入熱點 → 影響其他 query 延遲。
- **批次 commit**：被否決，需要在 reporter 內維護 buffer 與 flush 計時器，複雜度大於收益。simple async sleep + last-write-wins 已夠。
- **在 ORM 層加 hook**：被否決，污染 model 邊界。

理由：250 ms 對使用者視覺已足夠流暢（4 fps 進度條），同時把寫入頻率限制在 4 Hz。

### D4：每筆進度更新使用獨立短事務

選擇：`DbProgressReporter` 不持有長活 session；每次呼叫拿一個 short-lived async session、單一 `UPDATE pipeline_runs SET ... WHERE id=?`、立即 commit。

替代方案：
- **共用 session**：被否決。RQ worker 跑數十分鐘，長活 session 在 SQLite WAL 下會持有 read lock，影響其他 query。
- **背景批次寫**：被否決，重整復原會看到舊資料。

### D5：`PipelineRun` 表結構與索引

欄位：`id (UUID PK)`、`job_id (str)`、`status (enum)`、`triggered_by (str)`、`params (JSON)`、`current_stage (str|null)`、`current_stage_processed (int)`、`current_stage_total (int)`、`stage_summary (JSON)`、`error_message (text|null)`、`started_at`、`completed_at`、`created_at`。

索引：`(created_at DESC)`（list 用）、`(status)`（filter active 用）。

替代方案：
- **EAV / 子表存階段**：被否決，5 個階段固定、JSON 直接存最簡單，沒有複雜查詢需求。
- **`stage_summary` 拆成獨立表 `pipeline_run_stages`**：被否決，僅在做階段層級的跨 run 統計時才有價值，本 change 沒這需求。

### D6：trigger API response 擴充而非新增端點

選擇：保留 `POST /api/pipeline/trigger`，response 從 `{job_id}` 擴充為 `{job_id, run_id}`。先在 DB 建立 PipelineRun(queued)、再 enqueue 並把 run_id 帶入 worker job kwargs。

替代方案：
- **新增 `/api/pipeline/runs:create`**：被否決，多一個端點無實質好處，且需要前端遷移。
- **後端非同步建 row**：被否決，會出現「trigger 後 list 看不到」的 race condition。

理由：新增欄位是非破壞性擴充。先建 row 再 enqueue 確保「trigger 即可在 list 看到」。

### D7：前端輪詢策略分層

選擇：
- **runs list query**（`['pipeline-runs', 'list']`）：`staleTime: 30s` 預設不主動拉；偵測有 status=running run 時切換 `refetchInterval: 2000`。
- **active run detail query**（`['pipeline-runs', runId]`）：`refetchInterval: (data) => data?.status === 'running' ? 1000 : false`，跑完自動停。
- 視窗失焦時 React Query 預設不多輪詢，切回頁面自動 refetch — 與 SSE UX 等價。

替代方案：
- **固定間隔 2s 拉 list + 5s 拉 detail**：被否決，沒在跑時也持續打 DB 浪費。
- **WebSocket 即時推**：被否決（見 D1）。

### D8：進度回報的實際插入點在 stage job item loop

選擇：除 orchestrator 新增 `progress_reporter` 參數外，也修改 `run_ingestion_job`、`run_decryption_job`、`run_parse_job`、`run_classify_job`、`run_notify_job` 接受可選 reporter 或 stage-scoped callback。每個 stage job 在查出待處理 items 後呼叫 `stage_started(stage, total)`，在每筆 item 完成後呼叫 `stage_item_done(stage, processed)`，stage 結束時由 orchestrator 或 stage job 呼叫 `stage_finished(...)`，但同一 stage 不得重複 finished。

替代方案：
- **只在 orchestrator 呼叫 hook**：被否決。現有 orchestrator 只呼叫整個 stage job，無法知道 stage 內部每筆 item 何時完成，會讓進度條只能顯示階段級狀態。
- **先做假進度條**：被否決。使用者要判斷 stuck / running，假進度會誤導。
- **只做階段級進度**：可作為降級模式，但若 UI 顯示 `47 / 120`，spec 必須保證資料來自 stage job loop。

### D9：失敗語意分層，避免破壞 CLI / scheduler 行為

選擇：保留既有「單筆項目失敗不阻斷 stage」語意；新增明確分層：
- item-level failure：記入該 stage summary 的 fail count / errors，pipeline 可繼續，run status 可為 `succeeded_with_warnings` 或 `succeeded` 搭配 failed count（最終命名由 schema 決定）。
- stage crash / unexpected exception：`stage_finished` 記錄當下統計後，worker 將 run 標為 `failed`；CLI 路徑仍輸出既有 summary 或以既有 exception policy 處理，不得因 GUI change 無意改變 CLI stdout contract。
- RQ process crash：`on_failure_handler` 標 `failed`；後續 stale detector 列 future enhancement。

理由：目前 `_run_stage` catch 所有 exception 並轉成 failed summary。若新 spec 改成一律傳播 exception，會破壞「CLI / scheduler 路徑完全不變」的目標。需要先定義哪些錯誤應該讓 GUI run 失敗，哪些只是完成但有錯誤項目。

**附帶決策（D9.1）：worker job timeout 處理**

RQ 在 `worker.py` 設定 `job_timeout="30m"`（既有），長時間 pipeline 卡住時 RQ SHALL 觸發 `on_failure_handler`，其 SHALL 將 PipelineRun status 設為 `failed`、`error_message` 寫入含 `"job timeout"` 字樣、設 `completed_at`，避免 status 永久卡 `running` 讓 UI 一直顯示輪詢中。

替代方案：
- **不處理，等 stale detector 補洞**：被否決，本 change 沒做 stale detector，使用者會看到 run 永遠 running，UX 嚴重失準。
- **改寫 `job_timeout` 為更長時間（如 2h）**：被否決，超過 30m 的 pipeline 一定有問題，延長只是掩蓋。

理由：`on_failure_handler` 已存在且本 change 已要寫 status=failed，timeout 路徑不需新增 code path，僅要驗證 RQ 對 timeout 觸發的是同一 handler、且 `error_message` 能取得 timeout 訊號（從 `value: BaseException` 判斷型別）。Stale detector（依 `updated_at` 主動掃 stale running run）仍列為後續 enhancement。

### D10：scheduler 路徑刻意走 NoopProgressReporter，不寫 PipelineRun

選擇：APScheduler 觸發 `run_pipeline()` 時 SHALL **不**傳入 `progress_reporter`，預設使用 `NoopProgressReporter`，**不**在 `pipeline_runs` 表建立 row。UI 「歷史紀錄」卡片頂部 SHALL 顯示橫幅「僅手動觸發紀錄；scheduler 自動排程結果請查看 logs」，附 tooltip 說明此設計。

替代方案：
- **scheduler 也寫 PipelineRun**：被否決。需要 scheduler 程序與 worker 共用 RQ enqueue 流程（或 scheduler 直接寫 DB 後再走 worker），會耦合「scheduler 與 worker 必須同時健康」這條依賴；且 scheduler 既有 `bash scripts/pipeline.sh` 與 stdout JSON summary 是現有 audit trail，重複寫入 DB 是冗餘。
- **scheduler 走 RQ enqueue 與 API 同路徑**：可行但本 change 不做 — 會讓 scheduler 失去獨立性（worker 掛掉時 scheduler 也無法執行），違背 deployment 既有解耦設計。
- **UI 不揭露差異**：被否決，使用者會誤以為「我設了排程但歷史看不到 → 排程沒跑」，產生 false alarm。

理由：scope 收斂與既有解耦設計尊重。後續若 scheduler 也要寫 PipelineRun，新增 `triggered_by="scheduler"` 字面值即可（D2.1 已預留）。

### D11：Stage job loop hook 插入點 — 已驗證可行性

實作前 inspect 5 個 stage job 確認 hook 插入點，全部為單一 `for item in items:` 結構，無批次 flush / generator 障礙：

| Job | hook 插入點 | 結構 |
|---|---|---|
| `run_ingestion_job` | `backend/src/ccas/ingestor/job.py:404-430` | 三層 nested loop（bank → message → attachment），hook 點為最內層 attachment loop（line 422 附近） |
| `run_decryption_job` | `backend/src/ccas/decryptor/job.py:161-162` | 單層 `for attachment in attachments` |
| `run_parse_job` | `backend/src/ccas/parser/job.py:305-306` | 單層 `for attachment in attachments` |
| `run_classify_job` | `backend/src/ccas/classifier/job.py:61-63` | 單層 `for txn in transactions` |
| `run_notify_job` | `backend/src/ccas/bot/job.py:69-89` | 預先 extract ORM scalars 到 list、再 `for bill_id, ... in bill_rows` 逐筆 send |

理由：每個 job 都有清楚的 outer item loop，`stage_started(stage, total=len(items))` 可在 loop 之前呼叫、`stage_item_done(stage, processed=N)` 可在 loop 內每次 iteration 結束時呼叫；ingest 為三層 nested loop，total 應為「全部 bank 全部 message 全部 attachment 的 flatten 總數」，需在進入最外層之前先掃過取得 total（或退而求次：每個 bank 開始時呼叫 `stage_started(stage, total=current_bank_attachment_count)` 並接受跨 bank 時 total 會 reset，由前端容忍）。實作前 PR 中需在 description 列出每個 hook 的具體 file:line 與 total 計算方式。

## Risks / Trade-offs

- **節流可能漏顯示「最後一筆」**：[Risk] 階段最後一筆若卡在節流視窗 → Mitigation：`stage_finished` 一定即時寫，`current_stage_processed = current_stage_total` 在 finished hook 裡同步覆寫。
- **SQLite WAL 寫入熱點**：[Risk] 多階段同時更新 PipelineRun → Mitigation：pipeline 串列執行單一 run，同時間最多一個寫入者；250 ms 節流把寫入頻率壓到 4 Hz；每筆獨立短事務。
- **重整復原時 running 已過 1 小時**：[Risk] worker crash 後 status 卡 running → Mitigation：worker 端 try/except 包整個 run，crash 時走 `on_failure_handler` 標 status=failed；`pipeline_runs` 增加 `updated_at` 供未來 stale detector 使用；scheduler 加「超過 X 分鐘無進度更新自動標 stale」列為後續 enhancement（本 change 不做）。
- **同時兩個 trigger 競爭**：[Risk] 並發觸發兩個 run → Mitigation：RQ default queue 串列化（worker 同時只跑一個）；UI 在偵測到有 running run 時禁用「開始執行」按鈕（client-side guard，非強制）。
- **API response 擴充影響第三方 caller**：[Risk] 若有外部腳本依賴 `{job_id}`-only response → Mitigation：新增欄位向後相容；docs 註明 `run_id` 為新欄位、舊欄位保留。
- **alembic migration 與既有 db 衝突**：[Risk] 既有環境 alembic head 不一致 → Mitigation：本 change migration 僅新增表、無 alter 既有表；rollback = drop table，無破壞性。

## Deployment Integration

本 change 不新增任何 docker compose service、port、env var，但對既有部署架構有四個**隱含假設**，明文記錄於此以避免日後改動踩雷：

1. **共用 data volume**：backend / worker / scheduler / bot 四服務 SHALL 掛載同一個 host 目錄為 `/data`（dev compose 為 `./backend/data`、prod compose 為 `${CCAS_DATA_LOCATION:-./data}`）。`DbProgressReporter` 從 worker 寫入 `pipeline_runs` 表，需與 backend 讀取 API 共享同一份 SQLite WAL 檔。compose-pull-deploy 的 `docker-deployment` capability 已透過獨立 requirement 強制此約束。
2. **共用 redis service**：API 觸發走既有 RQ default queue（FastAPI 與 worker 連同一個 redis）。本 change 不新增 queue / channel。
3. **migration 由 backend 獨佔**：worker `command:` 直接跑 `rq worker`，不走 entrypoint → 不會與 backend 搶 alembic lock。新 migration（`add_pipeline_runs`）由 backend entrypoint `alembic upgrade head` 套用，`worker depends_on: backend: service_healthy` 確保 migration 完成後 worker 才上線。
4. **SQLite WAL 多 writer 並發**：`DbProgressReporter` 每筆獨立短事務 + 250 ms 節流，與 CCAS 既有 worker / scheduler 寫入模式一致。WAL 模式下 1 writer + N reader 為原生支援，本 change 不引入新瓶頸。

**遷移注意**：本 change 與 `compose-pull-deploy` 平行進行時，後者的 dev / prod compose 分流落地時 SHALL 對所有四個寫入 service 套用同一個 `${CCAS_DATA_LOCATION}` 變數，不得遺漏任一。

## Migration Plan

1. 建立 alembic migration，本機 + CI dry-run 過。
2. 後端先導：`PipelineRun` model + Protocol + DbProgressReporter + 改 orchestrator 注入點 + 改 worker + 新增 API endpoints + 測試。CLI 路徑自動走 noop，行為不變。
3. 前端後跟：`/operations` 頁面、nav 加按鈕、route lazy、Vitest + Playwright e2e。
4. 整合驗證：本機 `bash scripts/start.sh` 起 backend + frontend，跑 5-10 筆 pipeline，確認進度條與歷史正確；F5 復原行為符合預期。
5. PR 合入後，下一次 release（與 `compose-pull-deploy` 並列）即可。
6. **回滾**：alembic downgrade（drop table）、revert PR；CLI / scheduler 路徑因為走 noop，回滾後行為與 PR 前一致。

## Open Questions

- 是否要對 `triggered_by` 加 list filter UI — 本 change 不做，後續 enhancement。
- run 列表上限是否要做 cursor-based pagination — 本 change 預設 max 100、簡單 limit/offset 即可，後續再升級。
- 失敗 run 的 retry 機制 — out-of-scope，列入 Phase 2（取消 / 重跑）。
