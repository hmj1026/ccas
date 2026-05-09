## MODIFIED Requirements

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
