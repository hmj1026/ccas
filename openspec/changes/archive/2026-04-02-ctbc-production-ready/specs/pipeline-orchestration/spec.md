## MODIFIED Requirements

### Requirement: Notify 階段自主查詢未通知帳單

系統 SHALL 在 notify 階段自動查詢所有 `is_notified=False` 的帳單並發送 Telegram 通知，發送成功後標記為已通知。

#### Scenario: 新帳單自動通知
- **WHEN** parse 階段建立新的 Bill 記錄（`is_notified=False`）
- **THEN** notify 階段 SHALL 查詢到該帳單並發送 Telegram 通知

#### Scenario: 已通知帳單不重發
- **WHEN** Bill 的 `is_notified=True`
- **THEN** notify 階段 SHALL 跳過該帳單

#### Scenario: 通知成功後標記
- **WHEN** Telegram 通知發送成功
- **THEN** 系統 SHALL 將該 Bill 的 `is_notified` 設為 `True`

#### Scenario: 通知失敗不標記
- **WHEN** Telegram 通知發送失敗
- **THEN** `is_notified` SHALL 保持 `False`，下次 notify 會重試
