## ADDED Requirements

### Requirement: 付款提醒資料表模型
系統 SHALL 維持 `PaymentReminder` 資料模型的既有欄位與唯一約束，且 `sent_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### Scenario: 建立提醒紀錄
- **WHEN** 建立一筆 `PaymentReminder`
- **THEN** `sent_at` 會自動設定為 timezone-aware UTC datetime
