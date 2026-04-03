## MODIFIED Requirements

### Requirement: Docker 模式一鍵啟動

系統 SHALL 確保 `docker compose up` 為使用者提供完整的一鍵啟動體驗。開發模式透過 `docker-compose.override.yml` 自動覆寫 production 配置，啟動前自動驗證環境變數。

#### Scenario: docker compose up 啟動開發模式

- **WHEN** 使用者在專案根目錄執行 `docker compose up`（`docker-compose.override.yml` 存在）
- **THEN** Docker Compose SHALL 自動合併 override 檔，frontend 使用 Vite dev server（port 5173），backend 使用 dev target 含 hot reload

#### Scenario: docker compose 啟動 production 模式

- **WHEN** 使用者執行 `docker compose -f docker-compose.yaml up`（僅指定 base 檔）
- **THEN** frontend SHALL 使用 nginx production build（port 80），backend SHALL 使用 production target

#### Scenario: Docker 環境變數缺漏

- **WHEN** `.env` 缺少必要變數且執行 `docker compose up`
- **THEN** backend 容器 SHALL 在啟動階段輸出缺漏變數清單並以非零 exit code 退出
