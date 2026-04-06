## ADDED Requirements

### Requirement: Log persistence variables in .env.example

`.env.example` 文件說明日誌持久化相關環境變數。

#### Scenario: .env.example documents LOG_DIR
- **WHEN** 開發者查閱 `.env.example`
- **THEN** 可看到 `LOG_DIR`、`LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT`、`LOG_FILE_PREFIX` 的說明與預設值
