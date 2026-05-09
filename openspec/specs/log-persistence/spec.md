# log-persistence Specification

## Purpose
提供檔案型日誌持久化能力，讓日誌在容器重啟後仍可回溯。透過 RotatingFileHandler 實現大小型自動輪替，並支援多服務獨立檔名前綴。

## Requirements
### Requirement: File-based log persistence

`configure_logging()` SHALL 在 `log_dir` 設定為非空值時，除既有 `StreamHandler` 外同時掛載 `RotatingFileHandler`，將日誌寫入檔案；當 `log_dir` 為空字串時 SHALL 不建立任何 file handler，行為與既有 stdout-only logging 完全相同。

#### Scenario: log_dir is configured
- **WHEN** `Settings.log_dir` 為非空字串
- **THEN** `configure_logging()` 建立 `RotatingFileHandler` 寫入 `{log_dir}/{prefix}.log`

#### Scenario: log_dir is empty (default)
- **WHEN** `Settings.log_dir` 為空字串（預設值）
- **THEN** 不建立任何 file handler，行為與既有完全相同

### Requirement: Automatic log rotation

日誌檔案 SHALL 依大小自動輪替，避免磁碟空間無限成長；超過 `log_file_max_bytes` 時 SHALL 輪替並保留最多 `log_file_backup_count` 份備份；未指定 `LOG_FILE_MAX_BYTES` / `LOG_FILE_BACKUP_COUNT` 時 SHALL 採預設 10 MB / 5 份。

#### Scenario: log file exceeds max size
- **WHEN** 日誌檔案大小超過 `log_file_max_bytes`
- **THEN** `RotatingFileHandler` 自動輪替，保留最多 `log_file_backup_count` 份備份

#### Scenario: default rotation settings
- **WHEN** 未指定 `LOG_FILE_MAX_BYTES` 和 `LOG_FILE_BACKUP_COUNT`
- **THEN** 使用預設值 10 MB 和 5 份

### Requirement: File handler shares formatter and filter

檔案日誌 SHALL 與 stdout 日誌使用相同 formatter（含 JSON 格式選項）與機敏資訊遮罩 filter，避免機敏欄位以明文方式落地檔案。

#### Scenario: JSON format with redaction
- **WHEN** `log_format` 為 `json` 且日誌內容包含機敏資訊
- **THEN** file handler 輸出 JSON 格式且機敏欄位顯示為 `[REDACTED]`

### Requirement: Log directory auto-creation

若指定的 `log_dir` 不存在，`configure_logging()` SHALL 自動建立該目錄（含父目錄），避免容器啟動時因 mount 路徑尚未就緒而 crash。

#### Scenario: log directory does not exist
- **WHEN** `log_dir` 指向不存在的路徑
- **THEN** `configure_logging()` 自動建立該目錄（含父目錄）

### Requirement: Multi-service log file isolation

Docker 環境下多個服務共用同一 logs volume 時，各服務 SHALL 透過獨立的 `log_file_prefix`（如 `ccas-backend` / `ccas-worker`）寫入不同檔名，避免多服務同時寫同一檔案造成輪替衝突。

#### Scenario: multiple services write to same volume
- **WHEN** 多個容器掛載相同 logs 目錄
- **THEN** 各服務使用不同檔名前綴（如 `ccas-backend.log`、`ccas-worker.log`）避免衝突
