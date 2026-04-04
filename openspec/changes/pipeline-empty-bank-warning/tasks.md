## 1. 實作 ingest job 的空 banks 警告

- [x] 1.1 在 `backend/src/ccas/ingestor/job.py` 的 `run_ingestion_job()` 中，在 `_fetch_active_banks()` 呼叫後加入：若 `banks` 為空，append 診斷訊息到 `summary.errors`、`logger.warning(msg)` 並 `return summary`

## 2. 驗證

- [x] 2.1 清空 `bank_configs` 資料表後執行 `python -m ccas.pipeline --bank CTBC`，確認 output JSON 的 ingest.errors 含有診斷訊息
- [x] 2.2 重新執行 `python -m ccas.tools.bank_configs --apply` 後，確認 pipeline 正常跑完（errors 為空）
