# notification-delivery Specification

## Purpose
所有 Telegram 通知（新帳單通知、付款提醒、預算告警、解析失敗通知）共用的通知投遞規則：先認領再發送、失敗釋放認領、未設定時不認領。由 change deepen-notification-delivery 建立。

## Requirements
### Requirement: 單一通知投遞規則
系統 SHALL 以同一套投遞規則發送新帳單通知、付款提醒、預算告警與解析失敗通知。投遞的順序 SHALL 是：先認領（claim）通知事件，再發送 Telegram 訊息；發送成功後保留認領；發送失敗時釋放認領，讓下次執行重試。同一個通知事件 SHALL NOT 在成功送達後再次發送。

#### Scenario: 發送成功後不重送
- **WHEN** 某通知事件已成功送達，且同一事件在下次執行時再次符合發送條件
- **THEN** 系統 SHALL 判定為已投遞並略過，不再呼叫 Telegram

#### Scenario: 發送失敗後下次重試
- **WHEN** 某通知事件的 Telegram 發送拋出例外
- **THEN** 系統 SHALL 釋放該事件的認領
- **THEN** 下次執行時 SHALL 重新發送該事件剛好一次

#### Scenario: 釋放認領失敗
- **WHEN** 發送失敗後，釋放認領的資料庫操作也失敗
- **THEN** 系統 SHALL 記錄例外（含通知事件識別）並繼續處理其他事件，不中斷整批執行

### Requirement: Telegram 未設定時不認領
當 `TELEGRAM_BOT_TOKEN` 或 `TELEGRAM_CHAT_ID` 未設定時，系統 SHALL NOT 認領任何通知事件，也 SHALL NOT 呼叫 Telegram；投遞結果 SHALL 為「略過（未設定）」。設定補上後，先前未發送的通知事件 SHALL 在下次執行時發送。

#### Scenario: 未設定時略過且不留認領
- **WHEN** Telegram 未設定，且有待發送的通知事件
- **THEN** 系統 SHALL 不建立或更新任何認領紀錄
- **THEN** 投遞結果 SHALL 為「略過（未設定）」

#### Scenario: 補上設定後補送
- **WHEN** 先前因 Telegram 未設定而略過的通知事件，在設定補上後的下一次執行仍符合發送條件
- **THEN** 系統 SHALL 發送該事件

### Requirement: 通知事件的認領紀錄
每一種通知 SHALL 以下列既有或新增的紀錄作為認領：
- 新帳單通知與付款提醒：`payment_reminders` 的 `(bill_id, reminder_type)` 唯一鍵；認領為原子 INSERT，釋放為刪除該列。
- 預算告警：`budget_alerts.notified`；`notified=false` 的告警列即為待發送事件，成功後設為 `true`，失敗時維持 `false`。
- 解析失敗通知：`staged_attachments.failure_notified_at`；認領為原子條件更新（僅在欄位為空時設定時間），釋放為設回空值。

#### Scenario: 同一帳單同一提醒類型只有一筆認領
- **WHEN** 兩次執行同時嘗試認領同一帳單的同一提醒類型
- **THEN** 只有一次執行 SHALL 取得認領並發送

#### Scenario: 預算告警以單一行程為前提
- **WHEN** 預算告警評估由單一 APScheduler 行程執行
- **THEN** 同一告警 SHALL 不會被重複發送
- **THEN** 此前提 SHALL 記載於預算告警的認領實作文件中；若改為多個 worker 執行，須重新評估原子認領

### Requirement: 投遞結果
每次投遞 SHALL 回傳以下四種結果之一：已發送、已投遞（先前已送達而略過）、發送失敗（含錯誤）、略過（未設定）。各發送端 SHALL 依結果更新自己既有的統計，不改變對外回傳結構。

#### Scenario: 發送端統計不變
- **WHEN** notify stage、付款提醒或預算評估完成一次執行
- **THEN** 回傳結構 SHALL 與本變更前相同（`NotifySummary`、`{"sent","skipped"}`、`{"alerts_triggered","skipped"}`）
