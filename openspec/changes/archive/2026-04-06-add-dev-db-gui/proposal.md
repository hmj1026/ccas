## Why

開發與除錯時經常需要直接檢視 SQLite 資料庫內容和 Redis 快取狀態，目前只能透過 CLI 工具（`sqlite3`、`redis-cli`）操作，效率低且不直覺。新增 Web-based GUI 工具讓開發者可以透過瀏覽器快速瀏覽、查詢資料，大幅降低除錯門檻。

## What Changes

- 在 `docker-compose.override.yml` 新增 SQLite Web GUI 服務（sqlitewebui 或 sqlite-web）
- 在 `docker-compose.override.yml` 新增 Redis GUI 服務（RedisInsight 或 redis-commander）
- 新增開發者文件說明如何存取與使用這些 GUI 工具
- GUI 服務僅在開發環境（override）中啟用，不影響生產部署

## Capabilities

### New Capabilities

- `dev-gui-tools`: 開發環境 GUI 工具的 Docker Compose 服務定義、port 配置、volume 掛載規格

### Modified Capabilities

- `developer-onboarding`: 新增 GUI 工具的存取說明與使用指引

## Impact

- `docker-compose.override.yml`: 新增兩個服務定義
- `docs/`: 新增或更新開發者文件
- 新增兩個 Docker image 依賴（僅開發環境）
- Port 佔用：需分配兩個額外的本地端口
