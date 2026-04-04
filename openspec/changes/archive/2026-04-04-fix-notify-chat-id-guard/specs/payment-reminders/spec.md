## ADDED Requirements

### Requirement: Notify stage 在 chat_id 未設定時優雅跳過
`run_notify_job()` SHALL 在處理任何帳單前檢查 `settings.telegram_chat_id`，若為空則不嘗試發送任何 Telegram 訊息。

#### Scenario: telegram_chat_id 為空
- **WHEN** `TELEGRAM_CHAT_ID` 環境變數未設定或為空字串
- **THEN** notify job SHALL 立即回傳 `NotifySummary(sent_count=0, failed_count=0, errors=[])`
- **THEN** SHALL 寫入 INFO log 說明跳過原因
- **THEN** pipeline exit code SHALL 為 0（無失敗）
