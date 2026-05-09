# dev-gui-tools Specification

## Purpose
TBD - created by archiving change add-dev-db-gui. Update Purpose after archive.
## Requirements
### Requirement: SQLite Web GUI service

系統 SHALL 在 `docker-compose.yaml` 定義 `sqlite-web` 服務，使用 `coleifer/sqlite-web` image，標記 `profiles: [dev-tools]`。

服務 SHALL 將 host port `8088` 映射至 container port `8080`，並以 read-only 模式 bind mount `./backend/data:/data:ro`。

服務 SHALL 使用 `--read-only` flag 啟動，並自動開啟 `/data/ccas.db` 資料庫檔案。

服務 SHALL 設定 `depends_on: backend (service_healthy)`，確保 migration 完成後資料庫檔案才存在。

#### Scenario: 開發者存取 SQLite GUI

- **WHEN** 開發者執行 `docker compose --profile dev-tools up` 並瀏覽 `http://localhost:8088`
- **THEN** 顯示 sqlite-web 介面，可瀏覽 ccas.db 的所有表格與資料

#### Scenario: 資料庫 read-only 保護

- **WHEN** 開發者透過 sqlite-web 嘗試執行寫入操作
- **THEN** 操作失敗，因為 volume 以 read-only 模式掛載且服務以 `--read-only` 啟動

### Requirement: Redis GUI service

系統 SHALL 在 `docker-compose.yaml` 定義 `redis-commander` 服務，使用 `rediscommander/redis-commander` image，標記 `profiles: [dev-tools]`。

服務 SHALL 將 port `8081` 映射至 host。

服務 SHALL 透過 `REDIS_HOSTS` 環境變數自動連線至 `redis:6379`，啟動即用。

服務 SHALL 設定 `depends_on: redis (service_healthy)`，確保 Redis 可用後再啟動。

#### Scenario: 開發者存取 Redis GUI

- **WHEN** 開發者執行 `docker compose --profile dev-tools up` 並瀏覽 `http://localhost:8081`
- **THEN** 顯示 redis-commander 介面，自動連線至 Redis，可瀏覽所有 keys

### Requirement: GUI services are dev-tools profile only

GUI 服務 SHALL 標記 `profiles: [dev-tools]`，定義在 `docker-compose.yaml` 中。

預設執行 `docker compose up` 時 SHALL NOT 啟動任何 GUI 服務。

僅當指定 `--profile dev-tools` 時才啟動 GUI 服務。

#### Scenario: 預設啟動不含 GUI

- **WHEN** 使用 `docker compose up` 啟動（未指定 profile）
- **THEN** 不會啟動 sqlite-web 或 redis-commander 服務

#### Scenario: 開發者 opt-in 啟動 GUI

- **WHEN** 使用 `docker compose --profile dev-tools up` 啟動
- **THEN** sqlite-web 與 redis-commander 服務一併啟動

