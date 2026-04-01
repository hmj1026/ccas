## ADDED Requirements

### Requirement: SQLite Web GUI service

系統 SHALL 在 `docker-compose.override.yml` 定義 `sqlite-web` 服務，使用 `coleifer/sqlite-web` image。

服務 SHALL 將 port `8080` 映射至 host，並以 read-only 模式掛載 `ccas-data` volume。

服務 SHALL 在啟動時自動開啟 `/data/ccas.db` 資料庫檔案。

服務 SHALL 設定 `depends_on` 確保 backend 服務先啟動（資料庫檔案由 backend 建立）。

#### Scenario: 開發者存取 SQLite GUI

- **WHEN** 開發者執行 `docker compose up` 並瀏覽 `http://localhost:8080`
- **THEN** 顯示 sqlite-web 介面，可瀏覽 ccas.db 的所有表格與資料

#### Scenario: 資料庫 read-only 保護

- **WHEN** 開發者透過 sqlite-web 嘗試執行寫入操作
- **THEN** 操作失敗，因為 volume 以 read-only 模式掛載

### Requirement: Redis GUI service

系統 SHALL 在 `docker-compose.override.yml` 定義 `redisinsight` 服務，使用 `redis/redisinsight` image。

服務 SHALL 將 port `5540` 映射至 host。

服務 SHALL 設定 `depends_on` 等待 Redis 服務 healthy 後再啟動。

#### Scenario: 開發者存取 Redis GUI

- **WHEN** 開發者執行 `docker compose up` 並瀏覽 `http://localhost:5540`
- **THEN** 顯示 RedisInsight 介面，開發者可手動新增 `redis:6379` 連線

#### Scenario: Redis 連線可達

- **WHEN** 開發者在 RedisInsight 中新增連線，host 設定為 `redis`、port 為 `6379`
- **THEN** 連線成功，可瀏覽 Redis 中的所有 keys

### Requirement: GUI services are dev-only

GUI 服務 SHALL 僅定義在 `docker-compose.override.yml`，不出現在 `docker-compose.yaml`。

生產環境執行 `docker compose -f docker-compose.yaml up` 時 SHALL NOT 啟動任何 GUI 服務。

#### Scenario: 生產部署不含 GUI

- **WHEN** 使用 `docker compose -f docker-compose.yaml up` 啟動
- **THEN** 不會啟動 sqlite-web 或 redisinsight 服務
