# payment-reminders Specification

## Purpose
TBD - created by archiving change pipeline-scheduler. Update Purpose after archive.
## Requirements
### Requirement: 於帳單到期前 3 天發送付款提醒
系統 SHALL 每日執行一次排程工作，查詢 `due_date` 等於今日加 3 天的未付帳單，並透過 Telegram Bot 發送付款提醒通知。

#### Scenario: 找到到期前 3 天的未付帳單時發送提醒
- **WHEN** 3 天提醒排程工作執行，且資料庫中存在 `due_date` 等於今日加 3 天且尚未付款的帳單
- **THEN** 系統對每張符合條件的帳單觸發 Telegram 通知，包含銀行名稱、應繳金額與到期日

#### Scenario: 無符合條件的帳單時工作靜默完成
- **WHEN** 3 天提醒排程工作執行，但資料庫中無符合條件的未付帳單
- **THEN** 工作靜默完成，不發送任何通知，不記錄錯誤

### Requirement: 於帳單到期前 1 天發送付款提醒
系統 SHALL 每日執行一次排程工作，查詢 `due_date` 等於今日加 1 天的未付帳單，並透過 Telegram Bot 發送緊急付款提醒通知。

#### Scenario: 找到到期前 1 天的未付帳單時發送緊急提醒
- **WHEN** 1 天提醒排程工作執行，且資料庫中存在 `due_date` 等於今日加 1 天且尚未付款的帳單
- **THEN** 系統對每張符合條件的帳單觸發 Telegram 緊急通知，包含銀行名稱、應繳金額、到期日與明日到期的提示

#### Scenario: 無符合條件的帳單時工作靜默完成
- **WHEN** 1 天提醒排程工作執行，但資料庫中無符合條件的未付帳單
- **THEN** 工作靜默完成，不發送任何通知，不記錄錯誤

### Requirement: 防止同一帳單重複收到同類型提醒
系統 SHALL 確保同一張帳單不會因同一提醒類型（3 天或 1 天）在重複執行或系統重啟後收到超過一次的提醒通知。

#### Scenario: 已發送過 3 天提醒的帳單不再重複發送
- **WHEN** 3 天提醒排程工作再次執行，且某張帳單已在本次提醒週期內收到過 3 天提醒
- **THEN** 該帳單不會再次觸發 3 天提醒通知，工作略過該筆記錄

#### Scenario: 3 天提醒與 1 天提醒互相獨立
- **WHEN** 某張帳單已收到 3 天提醒通知
- **THEN** 當 1 天提醒排程工作執行且條件符合時，該帳單仍會收到 1 天提醒通知，不受 3 天提醒狀態影響

### Requirement: 付款提醒資料表模型
系統 SHALL 維持 `PaymentReminder` 資料模型的既有欄位與唯一約束，且 `sent_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### Scenario: 建立提醒紀錄
- **WHEN** 建立一筆 `PaymentReminder`
- **THEN** `sent_at` 會自動設定為 timezone-aware UTC datetime

