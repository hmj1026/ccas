# scheduler-jobs Specification

## Purpose
TBD - created by archiving change pipeline-scheduler. Update Purpose after archive.
## Requirements
### Requirement: 使用 RQ (Redis Queue) 執行排程工作
系統 SHALL 使用 RQ（Redis Queue）而非 APScheduler 在 FastAPI process 內執行排程工作。RQ job 應在獨立的 worker process 中執行，與 FastAPI server 分離。FastAPI 提供 `/api/pipeline/trigger` API endpoint 用於手動觸發 pipeline；定期觸發應透過 RQ scheduler 或外部 cron job 實現。

#### Scenario: RQ worker 在獨立 process 中執行 pipeline
- **WHEN** RQ worker 啟動並連線到 Redis
- **THEN** 系統可接收并執行 pipeline 任務，不阻塞 FastAPI server

#### Scenario: FastAPI 提供手動 pipeline 觸發端點
- **WHEN** POST `/api/pipeline/trigger` 被呼叫
- **THEN** 系統將 `run_pipeline()` 加入 RQ 工作隊列，立即回傳 job ID，工作在背景執行

### Requirement: Pipeline 工作失敗重試機制
系統 SHALL 為每個 pipeline RQ job 設定重試邏輯：最多重試 3 次，每次重試間隔採用指數退避（2^retry_count 秒，最多 60 秒）。重試計數器應記錄在 staging 表中。

#### Scenario: Job 首次失敗自動重試
- **WHEN** RQ job 執行 `run_pipeline()` 並拋出例外
- **THEN** 系統自動重試該 job，重試次數不超過 3 次

#### Scenario: 重試達上限後標記為 manual_review_needed
- **WHEN** pipeline job 的重試次數達到 3 次仍失敗
- **THEN** 系統將該 job 對應的所有 staging 項目狀態標記為 `manual_review_needed`，停止進一步自動重試，管理者可手動檢視並補救

#### Scenario: 重試間隔採用指數退避
- **WHEN** 重試次數為 0, 1, 2
- **THEN** 重試延遲分別為 1s, 2s, 4s（即 2^retry_count，上限 60s）

### Requirement: 週期性觸發方式（外部 cron 或 APScheduler 佐助）
系統 SHALL **不在 FastAPI process 內啟動 APScheduler**。定期觸發 pipeline SHALL 透過以下其中一種方式實現：
1. **外部 cron job** — 定期呼叫 `curl /api/pipeline/trigger`（推薦用於生產環境）
2. **CLI 命令** — `python -m ccas.scheduler` 啟動一個獨立的輕量排程服務（使用 APScheduler），該服務與 FastAPI 和 RQ worker 分別運行

Scheduler 觸發 API 時 SHALL 使用 `SCHEDULER_API_BASE_URL` 環境變數（若已設定）作為 backend API 的基礎 URL。當該變數未設定或為空時，SHALL fallback 到 `http://{api_host}:{api_port}`。此設計分離 server binding address 與 client request URL，確保 Docker 環境下 scheduler 容器能正確路由至 backend 容器。

#### Scenario: Cron job 定期觸發 pipeline
- **WHEN** 系統 cron 設定為每日午夜執行 `curl -X POST http://localhost:8000/api/pipeline/trigger -H "Authorization: Bearer $API_TOKEN"`
- **THEN** pipeline 會定期啟動，RQ job 在 worker 執行

#### Scenario: CLI 排程器啟動獨立 APScheduler
- **WHEN** 執行 `python -m ccas.scheduler` 並配置定期時間
- **THEN** 獨立進程啟動 APScheduler，定期呼叫 `/api/pipeline/trigger` 或直接向 RQ 隊列推送工作

#### Scenario: Docker 環境下 scheduler 使用 SCHEDULER_API_BASE_URL
- **WHEN** 環境變數 `SCHEDULER_API_BASE_URL` 設定為 `http://backend:8000`
- **THEN** scheduler 觸發 pipeline 時 SHALL 發送 POST 請求至 `http://backend:8000/api/pipeline/trigger`

#### Scenario: 本地開發環境 fallback 到 api_host
- **WHEN** `SCHEDULER_API_BASE_URL` 未設定或為空字串
- **THEN** scheduler 觸發 pipeline 時 SHALL 發送 POST 請求至 `http://{api_host}:{api_port}/api/pipeline/trigger`

