## Context

CCAS 使用 SQLite (WAL mode) 作為主要資料庫，Redis 作為排程與快取。目前開發者只能透過 `sqlite3` CLI 和 `redis-cli` 查看資料，缺乏視覺化工具。

GUI 服務透過 Docker Compose **profiles** 機制管理，開發者 opt-in 啟動，不影響預設的 `docker compose up` 或 QA 流程。

## Goals / Non-Goals

**Goals:**
- 提供瀏覽器可存取的 SQLite GUI，支援瀏覽表格、執行查詢
- 提供瀏覽器可存取的 Redis GUI，支援瀏覽 keys、檢視值
- 僅在開發者主動啟用時載入（`--profile dev-tools`），不影響生產或 QA 配置
- 新增文件讓開發者快速上手（含本地非 Docker 替代方案）

**Non-Goals:**
- 不提供寫入/修改資料的 GUI 操作建議（純檢視用途）
- 不變更生產環境的服務定義
- 不新增額外的認證機制（本地開發環境無需認證）

## Decisions

### 部署機制: Docker Compose profiles

選擇 `profiles: [dev-tools]` 取代 `docker-compose.override.yml`：
- `docker compose up` 預設不啟動 GUI 服務（QA 不受影響）
- 開發者透過 `docker compose --profile dev-tools up` 明確 opt-in
- 服務定義集中在 `docker-compose.yaml`，符合 SSOT 原則
- 不需維護額外的 override 檔案

### SQLite GUI: sqlite-web

選擇 `coleifer/sqlite-web` image：
- 輕量、單一用途，專為 SQLite 設計
- 支援瀏覽表結構、執行 SQL 查詢、匯出資料
- Docker image 小（基於 Alpine）
- 使用 `--read-only` flag + `:ro` volume mount 雙重防護
- 透過 bind mount `./backend/data:/data:ro` 存取資料庫（與其他服務一致）

### Redis GUI: redis-commander

選擇 `rediscommander/redis-commander` 取代 RedisInsight：
- 透過 `REDIS_HOSTS` 環境變數自動連線，啟動即用
- 不需每次容器重建後手動設定連線
- 輕量、單一用途

### Port 分配

| Service | Host Port | Container Port | URL |
|---------|-----------|----------------|-----|
| sqlite-web | 8088 | 8080 | http://localhost:8088 |
| redis-commander | 8081 | 8081 | http://localhost:8081 |

Port 選擇避開常用的 8080，降低衝突風險。

### Volume 存取

- `sqlite-web` 使用 bind mount `./backend/data:/data:ro`（與 backend 等服務相同路徑，加 `:ro` 防寫入）
- `redis-commander` 透過 Docker 網路連線至 Redis 服務，不需額外 volume

### 啟動依賴

- `sqlite-web` depends_on `backend` (service_healthy) — 確保 entrypoint 完成 migration 後 DB 檔案才存在
- `redis-commander` depends_on `redis` (service_healthy) — 確保 Redis 可用

## Risks / Trade-offs

- **Port 衝突**: 8088 和 8081 仍可能與其他本地服務衝突。透過文件說明替代方案（修改 port mapping）。
- **sqlite-web 寫入風險**: 透過 `--read-only` flag 與 `:ro` volume mount 雙重防護。
- **redis-commander 資料持久化**: 設定資料存在容器內，重建容器後書籤等資料會消失。對開發工具可接受。
- **本地開發不可用**: GUI 工具依賴 Docker。文件補充本地替代方案（VS Code SQLite Viewer、sqlite3 CLI）。
