## MODIFIED Requirements

### Requirement: Staging 路徑跨環境一致性

`staged_attachments.staged_path` SHALL 儲存相對於 `STAGING_DIR` 的相對路徑（如 `FUBON/xxx.pdf`），而非絕對路徑。使用時 SHALL 以 `Path(settings.staging_dir) / staged_path` 組合為完整路徑。

#### Scenario: 新建 staging record 使用相對路徑
- **WHEN** ingest job 建立新的 `StagedAttachment` record
- **THEN** `staged_path` SHALL 為相對路徑格式（如 `FUBON/msg123_file.pdf`），不含 STAGING_DIR prefix

#### Scenario: 讀取時動態組合完整路徑
- **WHEN** decrypt job 或 parse job 讀取 `staged_path`
- **THEN** SHALL 以 `Path(settings.staging_dir) / staged_path` 取得完整檔案路徑

#### Scenario: Docker 與本機環境均可正常存取
- **WHEN** 同一筆 staging record 在 Docker（`STAGING_DIR=/data/staging`）與本機（`STAGING_DIR=./data/staging`）執行
- **THEN** 兩環境 SHALL 皆能正確定位檔案

#### Scenario: 既有記錄 migration
- **WHEN** 執行路徑 migration script
- **THEN** 既有的絕對路徑 record SHALL 被轉換為相對路徑，script SHALL 為 idempotent（重複執行不重複修改）
