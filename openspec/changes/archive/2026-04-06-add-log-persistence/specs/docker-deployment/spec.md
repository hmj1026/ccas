## ADDED Requirements

### Requirement: Logs bind mount for persistence

Docker Compose 使用 bind mount 將專案根目錄 `./logs/` 掛載至容器內 `/logs`，搭配 `logs/.gitkeep` 確保目錄存在於 git。

#### Scenario: container restart preserves logs
- **WHEN** 任一服務容器重啟
- **THEN** 先前的日誌檔案仍保留在 host 的 `./logs/` 目錄中

#### Scenario: all services mount logs directory
- **WHEN** docker-compose up 啟動所有服務
- **THEN** backend、worker、scheduler、bot 均掛載 `./logs:/logs`

#### Scenario: services use independent log file prefixes
- **WHEN** 多個服務同時寫入 `/logs` 目錄
- **THEN** 各服務透過 `LOG_FILE_PREFIX` 環境變數寫入獨立檔案（`ccas-backend.log`、`ccas-worker.log`、`ccas-scheduler.log`、`ccas-bot.log`）

### Requirement: LOG_DIR in shared environment

`x-shared-env` anchor 中加入 `LOG_DIR` 設定。

#### Scenario: shared-env includes LOG_DIR
- **WHEN** 服務使用 `<<: *shared-env`
- **THEN** `LOG_DIR` 被設定為 `/logs`
