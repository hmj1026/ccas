# telegram-notifications Specification

## Purpose
TBD - created by archiving change telegram-bot. Update Purpose after archive.
## Requirements
### Requirement: 新帳單解析完成時推播摘要
系統 SHALL 在新帳單解析完成後主動發送 Telegram 摘要訊息，至少包含銀行、帳單月份、應繳金額與到期日。

#### Scenario: 發送新帳單摘要通知
- **WHEN** 某份帳單成功解析並寫入資料庫
- **THEN** 系統會向設定的 Telegram chat 發送一則新帳單摘要通知

### Requirement: 到期前 3 天與 1 天發送未繳提醒
系統 SHALL 對尚未繳款的帳單，在到期日前 3 天與 1 天各發送一次提醒。

#### Scenario: 到期前 3 天發送提醒
- **WHEN** 某筆未繳帳單距離到期日還有 3 天
- **THEN** 系統會發送提醒訊息，包含帳單金額與到期日

#### Scenario: 到期前 1 天發送提醒
- **WHEN** 某筆未繳帳單距離到期日還有 1 天
- **THEN** 系統會再次發送提醒訊息

### Requirement: 解析失敗時發送異常通知
系統 SHALL 在帳單附件解析失敗時發送 Telegram 通知，提示需要人工處理。通知 SHALL 由 pipeline notify stage 發送：notify stage 在處理新帳單通知後，找出狀態為 `parse_failed` 且尚未通知（`failure_notified_at` 為空）的帳單附件，合併成一則訊息發送。每一份解析失敗的帳單附件 SHALL 最多成功通知一次，即使 parser 在後續執行中再次重試並失敗。

#### Scenario: 發送解析失敗通知
- **WHEN** 某個 staged attachment 的解析狀態變為 `parse_failed`，且下一次 notify stage 執行時 Telegram 已設定
- **THEN** 系統會發送包含銀行資訊、檔案名稱與失敗摘要的異常通知
- **THEN** 該附件的 `failure_notified_at` SHALL 被設定

#### Scenario: 多份附件合併為一則訊息
- **WHEN** 同一次 notify stage 有 3 份尚未通知的解析失敗附件
- **THEN** 系統 SHALL 只發送一則訊息，內容列出 3 份附件

#### Scenario: 重試仍失敗時不重複通知
- **WHEN** 已通知過的解析失敗附件在後續 pipeline 執行中再次解析失敗
- **THEN** 系統 SHALL NOT 再次發送該附件的解析失敗通知

#### Scenario: 發送失敗時下次補送
- **WHEN** 解析失敗通知的 Telegram 發送拋出例外
- **THEN** 該訊息涵蓋的附件 SHALL 回到尚未通知狀態（`failure_notified_at` 為空）
- **THEN** 下次 notify stage SHALL 再次發送

### Requirement: 新帳單通知發送失敗時重試
新帳單通知 SHALL 遵守通知投遞規則：發送失敗時釋放該帳單的認領，下次 notify stage 執行時重新發送；發送成功後 SHALL NOT 重送。

#### Scenario: 第一次發送失敗，第二次補送
- **WHEN** 某新帳單的通知第一次發送失敗，且下一次 notify stage 執行時發送成功
- **THEN** 該帳單 SHALL 剛好收到一則新帳單通知
- **THEN** 該帳單 SHALL 被標記為 `is_notified=true`
