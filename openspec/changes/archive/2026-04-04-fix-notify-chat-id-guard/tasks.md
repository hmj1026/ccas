## 1. 實作 chat_id guard

- [x] 1.1 在 `backend/src/ccas/bot/job.py` 的 `run_notify_job()` 中，在 `stmt = select(Bill)...` 前加入：
  ```python
  if not settings.telegram_chat_id:
      logger.info("TELEGRAM_CHAT_ID 未設定，跳過 notify stage")
      return summary
  ```

## 2. 驗證

- [x] 2.1 在 `TELEGRAM_CHAT_ID=` 空值環境下執行 pipeline，確認 notify stage `sent=0, failed=0, errors=[]`，exit code 0
