## Context

`settings.telegram_chat_id` 預設為 `""` 。`run_notify_job()` 未在呼叫 Telegram API 前驗證此值。`send_message` 傳入空字串給 Telegram，回傳 HTTP 400。

## Goals / Non-Goals

**Goals:**
- `telegram_chat_id` 為空時，notify job 優雅跳過（`sent=0, failed=0`）並記錄 INFO log

**Non-Goals:**
- 不修改 `send_message()` 本身
- 不改變 notify job 有正確 chat_id 時的行為

## Decisions

**D1 — 在查詢帳單之前加入 chat_id guard**

```python
if not settings.telegram_chat_id:
    logger.info("TELEGRAM_CHAT_ID 未設定，跳過 notify stage")
    return summary
```

## Risks / Trade-offs

- [Risk] 用戶誤以為 notify 成功 → Mitigation: INFO log 明確說明跳過原因
