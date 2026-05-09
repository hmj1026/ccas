## Why

Pipeline 在 `bank_configs` 資料表為空時，ingest stage 靜默返回 `staged: 0`，沒有任何警告或錯誤。新用戶若忘記執行 `python -m ccas.tools.bank_configs --apply`，會看到所有 stage 均為 0 的輸出而不知道原因，難以排查。

## What Changes

- `ingest` job 在查詢 active banks 後，若結果為空，寫入一條 `WARNING` log 並在 summary.errors 中加入說明訊息
- 不改變 pipeline 的 exit code（仍為 0，因為技術上沒有失敗）

## Capabilities

### New Capabilities
<!-- 無新 capability -->

### Modified Capabilities
- `pipeline-options`: ingest stage 的診斷行為改變

## Impact

- `backend/src/ccas/ingestor/job.py` — `run_ingestion_job()` 在無 active banks 時加 warning
