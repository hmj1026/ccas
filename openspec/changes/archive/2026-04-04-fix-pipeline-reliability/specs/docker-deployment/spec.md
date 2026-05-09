## ADDED Requirements

### Requirement: RQ Worker 服務定義

系統 SHALL 在 `docker-compose.yaml` 定義一個 `worker` 服務，負責消費 Redis Queue 中的 pipeline 任務。Worker 服務 SHALL 使用與 backend 相同的 build context 與 production target，共用相同的 volumes、env_file 與 shared environment。

#### Scenario: Worker 服務存在於 Docker Compose 配置

- **WHEN** 執行 `docker compose config`
- **THEN** 輸出 SHALL 包含名為 `worker` 的服務定義

#### Scenario: Worker 在 backend 就緒後啟動

- **WHEN** `docker compose up` 啟動所有服務
- **THEN** `worker` 服務 SHALL 等待 `backend`（service_healthy）與 `redis`（service_healthy）就緒後才啟動

#### Scenario: Worker 消費佇列中的 pipeline 任務

- **WHEN** `/api/pipeline/trigger` 端點將任務排入 Redis Queue
- **THEN** `worker` 服務 SHALL 從佇列取出並執行 `run_pipeline_sync`，任務不會無限期滯留在 Redis 中

#### Scenario: Worker 異常終止後自動重啟

- **WHEN** `worker` 服務非預期終止
- **THEN** Docker Compose SHALL 依 `restart: unless-stopped` 策略自動重啟 worker
