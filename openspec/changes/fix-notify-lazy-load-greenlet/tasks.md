## 1. 修正 ORM 屬性存取順序

- [x] 1.1 在 `backend/src/ccas/bot/job.py` 的 `run_notify_job()` 中，確認 `bill_id`、`bill_code`、`bill_month` 的賦值位於 for 迴圈的最開始（try 塊外），並在任何 `await session.*` 操作前完成
- [x] 1.2 在 except 塊中使用已緩存的本地變數（不再存取 `bill.` 屬性）

## 2. 驗證

- [x] 2.1 設定有效 TELEGRAM_CHAT_ID 後，人工使 notify 對第一個帳單失敗，確認後續帳單仍可嘗試發送而不拋出 MissingGreenlet
