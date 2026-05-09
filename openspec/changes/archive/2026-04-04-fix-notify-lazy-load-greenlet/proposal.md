## Why

`run_notify_job()` 在 Telegram 發送失敗後呼叫 `await session.rollback()`，但 SQLAlchemy async session 在 rollback 後會 expire 所有 session-bound 物件。下一個 for 迴圈迭代存取 `bill.id` 時觸發 lazy loading，但 async 環境沒有 greenlet context，導致 `sqlalchemy.exc.MissingGreenlet` exception，整個 notify stage crash。

## What Changes

- 在 for 迴圈的最開始，將 `bill` 的所有需要欄位（`id`、`bank_code`、`billing_month`）讀取到本地變數，避免在 session 操作後再存取 ORM 屬性

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `payment-reminders`: notify job 的 ORM 屬性存取順序改變

## Impact

- `backend/src/ccas/bot/job.py` — 重排 `run_notify_job()` 中的屬性存取與 session 操作順序
