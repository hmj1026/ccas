## 1. Docker Compose 服務定義

- [x] 1.1 在 `docker-compose.yaml` 新增 `sqlite-web` 服務：`profiles: [dev-tools]`，bind mount `./backend/data:/data:ro`，port `8088→8080`，depends_on backend (service_healthy)，`--read-only` flag
- [x] 1.2 在 `docker-compose.yaml` 新增 `redis-commander` 服務：`profiles: [dev-tools]`，`REDIS_HOSTS` env var 自動連線，port `8081`，depends_on redis (service_healthy)

## 2. 驗證

- [x] 2.1 執行 `docker compose config` 驗證合併後的配置語法正確
- [x] 2.2 確認 `docker compose up` 不啟動 GUI 服務（profiles 未指定時不載入）
- [x] 2.3 確認 `docker compose --profile dev-tools up` 啟動 GUI 服務
  - sqlite-web: HTTP 200, 載入 ccas.db, read-only 保護生效（`attempt to write a readonly database`）
  - redis-commander: HTTP 200, 自動連線 Redis 7.4.8 成功
  - 注意: 兩個 image 為 linux/amd64，在 ARM Mac 上透過 Rosetta 運行（有平台警告但功能正常）

## 3. 文件

- [x] 3.1 在 `docs/developer-guide.md` 更新開發工具文件，包含：Docker GUI 啟動方式（`--profile dev-tools`）、存取 URL、本地替代方案（VS Code SQLite Viewer、sqlite3 CLI）
- [x] 3.2 文件包含 port 衝突排解說明與自訂 port 方法
