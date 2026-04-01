## Context

CCAS 使用 SQLite (WAL mode) 作為主要資料庫，Redis 作為排程與快取。目前開發者只能透過 `sqlite3` CLI 和 `redis-cli` 查看資料，缺乏視覺化工具。

現有 `docker-compose.override.yml` 已為開發環境提供 bind-mount 與 hot reload 設定，新增 GUI 服務應延續此模式。

## Goals / Non-Goals

**Goals:**
- 提供瀏覽器可存取的 SQLite GUI，支援瀏覽表格、執行查詢
- 提供瀏覽器可存取的 Redis GUI，支援瀏覽 keys、檢視值
- 僅在開發環境啟用（docker-compose.override.yml），不影響生產配置
- 新增文件讓開發者快速上手

**Non-Goals:**
- 不提供寫入/修改資料的 GUI 操作建議（純檢視用途）
- 不變更生產環境的 docker-compose.yaml
- 不新增額外的認證機制（本地開發環境無需認證）

## Decisions

### SQLite GUI: sqlite-web

選擇 `coleifer/sqlite-web` image：
- 輕量、單一用途，專為 SQLite 設計
- 支援瀏覽表結構、執行 SQL 查詢、匯出資料
- Docker image 小（基於 Alpine）
- Port: `8080`
- 掛載 `ccas-data` volume 以存取 `/data/ccas.db`

### Redis GUI: RedisInsight

選擇 `redis/redisinsight` image：
- Redis 官方出品，功能完整
- 支援 key 瀏覽、記憶體分析、慢查詢檢視
- Port: `5540`（RedisInsight 預設）
- 透過 `REDIS_URL` 環境變數或手動設定連線至 `redis:6379`

### Port 分配

| Service | Port | URL |
|---------|------|-----|
| sqlite-web | 8080 | http://localhost:8080 |
| RedisInsight | 5540 | http://localhost:5540 |

### Volume 存取

- `sqlite-web` 需要以 read-only 方式掛載 `ccas-data` volume（`:ro`）以避免意外寫入
- `RedisInsight` 透過網路連線至 Redis 服務，不需額外 volume

## Risks / Trade-offs

- **Port 衝突**: 8080 和 5540 可能與其他本地服務衝突。透過文件說明替代方案。
- **sqlite-web 寫入風險**: 雖然 sqlite-web 預設允許寫入，但透過 read-only volume mount 防止意外修改。
- **RedisInsight 資料持久化**: RedisInsight 設定資料預設存在容器內，重建容器後需重新設定連線。可用 named volume 解決，但為簡化配置暫不處理。
