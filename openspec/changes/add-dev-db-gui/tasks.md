## 1. Docker Compose 服務定義

- [ ] 1.1 在 `docker-compose.override.yml` 新增 `sqlite-web` 服務：使用 `coleifer/sqlite-web` image，port `8080`，read-only 掛載 `ccas-data` volume，depends_on backend
- [ ] 1.2 在 `docker-compose.override.yml` 新增 `redisinsight` 服務：使用 `redis/redisinsight` image，port `5540`，depends_on redis (healthy)

## 2. 驗證

- [ ] 2.1 執行 `docker compose config` 驗證合併後的配置語法正確
- [ ] 2.2 確認 `docker compose -f docker-compose.yaml config` 不包含 GUI 服務

## 3. 文件

- [ ] 3.1 在 `docs/` 新增或更新開發工具文件，包含 GUI 工具清單、存取 URL、RedisInsight 連線設定步驟
- [ ] 3.2 文件包含 port 衝突排解說明與自訂 port 方法
