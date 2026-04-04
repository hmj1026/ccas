## ADDED Requirements

### Requirement: Ingest stage 無 active banks 時的診斷警告
當 `run_ingestion_job()` 查詢後發現無任何啟用的銀行設定，pipeline SHALL 在 `IngestionSummary.errors` 中加入診斷訊息，並寫入 WARNING 等級的 log，說明如何初始化銀行設定。

#### Scenario: bank_configs 資料表為空
- **WHEN** `bank_configs` 資料表中無任何 `is_active=True` 的記錄
- **THEN** `run_ingestion_job()` SHALL 在 `summary.errors` 加入訊息 `"[Ingest] 未找到任何啟用的銀行設定。請先執行 python -m ccas.tools.bank_configs --apply 初始化銀行設定。"`
- **THEN** WARNING log SHALL 寫入相同訊息
- **THEN** pipeline 仍以 exit code 0 完成（staged=0, errors=[訊息]）
