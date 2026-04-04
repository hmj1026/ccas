## Why

`run_notify_job()` 在 `settings.telegram_chat_id` 為空字串時，仍嘗試呼叫 Telegram API 傳送訊息，導致 HTTP 400 Bad Request（Telegram 不接受空 chat_id）。Pipeline 因此記錄所有帳單為 notify 失敗，exit code 為 1。此情況本應視為「Telegram 未設定，跳過通知」而非錯誤。

## What Changes

- `run_notify_job()` 在處理帳單前先檢查 `settings.telegram_chat_id`，若為空則寫入警告 log 並直接回傳空 summary（不計為失敗）

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `payment-reminders`: notify stage 的 chat_id 空值行為改變

## Impact

- `backend/src/ccas/bot/job.py` — `run_notify_job()` 加入 chat_id 空值早退檢查
