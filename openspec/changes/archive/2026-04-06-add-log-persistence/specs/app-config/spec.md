## ADDED Requirements

### Requirement: Log persistence configuration fields

Settings 類別新增日誌持久化相關欄位。

#### Scenario: LOG_DIR configures log directory
- **WHEN** 環境變數 `LOG_DIR` 設為 `/logs`
- **THEN** `Settings.log_dir` 返回 `"/logs"`

#### Scenario: LOG_DIR defaults to empty
- **WHEN** 未設定 `LOG_DIR` 環境變數
- **THEN** `Settings.log_dir` 返回空字串（停用檔案日誌）

#### Scenario: LOG_FILE_MAX_BYTES configures rotation size
- **WHEN** 環境變數 `LOG_FILE_MAX_BYTES` 設為 `5242880`
- **THEN** `Settings.log_file_max_bytes` 返回 `5242880`

#### Scenario: LOG_FILE_BACKUP_COUNT configures backup count
- **WHEN** 環境變數 `LOG_FILE_BACKUP_COUNT` 設為 `3`
- **THEN** `Settings.log_file_backup_count` 返回 `3`

#### Scenario: LOG_FILE_PREFIX configures log filename prefix
- **WHEN** 環境變數 `LOG_FILE_PREFIX` 設為 `ccas-worker`
- **THEN** `Settings.log_file_prefix` 返回 `"ccas-worker"`

#### Scenario: LOG_FILE_PREFIX defaults to ccas
- **WHEN** 未設定 `LOG_FILE_PREFIX` 環境變數
- **THEN** `Settings.log_file_prefix` 返回 `"ccas"`

#### Scenario: LOG_FILE_MAX_BYTES rejects zero or negative
- **WHEN** 環境變數 `LOG_FILE_MAX_BYTES` 設為 `0` 或負數
- **THEN** pydantic 驗證失敗（`gt=0`）
