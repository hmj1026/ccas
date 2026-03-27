## ADDED Requirements

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
系統 SHALL 在帳單附件解析失敗時發送 Telegram 通知，提示需要人工處理。

#### Scenario: 發送解析失敗通知
- **WHEN** 某個 staged attachment 的解析狀態變為 `parse_failed`
- **THEN** 系統會發送包含銀行資訊與失敗摘要的異常通知
