## ADDED Requirements

### Requirement: Logs volume for persistence

Docker Compose 新增 named volume 供所有服務掛載日誌目錄。

#### Scenario: container restart preserves logs
- **WHEN** 任一服務容器重啟
- **THEN** 先前的日誌檔案仍保留在 `ccas-logs` volume 中

#### Scenario: all services mount logs volume
- **WHEN** docker-compose up 啟動所有服務
- **THEN** backend、worker、scheduler、bot 均掛載 `ccas-logs:/logs`

### Requirement: LOG_DIR in shared environment

`x-shared-env` anchor 中加入 `LOG_DIR` 設定。

#### Scenario: shared-env includes LOG_DIR
- **WHEN** 服務使用 `<<: *shared-env`
- **THEN** `LOG_DIR` 被設定為 `/logs`
