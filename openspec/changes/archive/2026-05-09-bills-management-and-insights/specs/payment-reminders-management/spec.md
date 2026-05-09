## ADDED Requirements

### Requirement: GET /api/reminders/settings 列出付款提醒

系統 SHALL 提供 `GET /api/reminders/settings` 端點，回傳所有 `PaymentReminder`（既有 model）含關聯的 `Bill` 元資料（bank、period、due_date、total_amount）與當前提醒設定（enabled、days_before、channel）。Response SHALL 為陣列、按 due_date ASC 排序、僅包含「未來 60 天內 due 的 bills」（不含已過期）。

#### Scenario: 列出未到期帳單的提醒

- **WHEN** 前端呼叫 `GET /api/reminders/settings`
- **THEN** response SHALL 含未來 60 天內到期的 bill 對應 reminder、含完整 reminder 設定欄位

#### Scenario: 過期 bill 不出現在列表

- **WHEN** 某 bill due_date 已過 7 天
- **THEN** SHALL 不出現在 `GET /api/reminders/settings` 回應中（避免列表噪音）

### Requirement: PUT /api/reminders/{bill_id}/settings 更新提醒

系統 SHALL 提供 `PUT /api/reminders/{bill_id}/settings` 端點 body `{enabled?, days_before?, channel?}`，partial update 對應 PaymentReminder。`channel` enum SHALL 含 `telegram`、`ui_banner`、`both`、`none`。

#### Scenario: 啟用 reminder

- **WHEN** body `{enabled: true, days_before: 3, channel: "telegram"}`
- **THEN** 系統 SHALL UPDATE 對應 reminder、回 200

#### Scenario: 不存在的 bill 回 404

- **WHEN** `PUT /api/reminders/99999/settings`、bill 不存在
- **THEN** SHALL 回 404

#### Scenario: 422 invalid days_before

- **WHEN** body `{days_before: -5}`
- **THEN** SHALL 回 422、錯誤訊息「days_before 必須為非負整數」

#### Scenario: 422 invalid channel

- **WHEN** body `{channel: "email"}`（不在 enum 內）
- **THEN** SHALL 回 422

### Requirement: POST /api/reminders/{bill_id}/test 立即測試發送

系統 SHALL 提供 `POST /api/reminders/{bill_id}/test` 端點，立即推送一次提醒到該 reminder 設定的 channel（不影響真實 schedule、不寫入歷史）。回 `{sent: bool, channel: str, error?: str}`。

#### Scenario: 測試 telegram 推送

- **WHEN** reminder.channel="telegram"、Telegram bot 已連線、使用者點「測試發送」
- **THEN** 系統 SHALL 推一則測試訊息到設定的 chat_id、回 `{sent: true, channel: "telegram"}`、訊息內容明示「[測試] 帳單提醒：...」

#### Scenario: telegram disabled 時錯誤訊息明確

- **WHEN** reminder.channel="telegram"、Telegram token 未設定
- **THEN** SHALL 回 `{sent: false, channel: "telegram", error: "Telegram bot 未設定，請在 .env 加入 TELEGRAM_BOT_TOKEN"}`

#### Scenario: ui_banner 測試只觸發 ui 端

- **WHEN** reminder.channel="ui_banner"、使用者點測試
- **THEN** SHALL 寫入暫時 ui_banner 紀錄（10 分鐘 TTL）、回 `{sent: true, channel: "ui_banner"}`、前端 dashboard 載入時可見「[測試] ...」banner

### Requirement: /settings/reminders 前端頁面

系統 SHALL 提供 `frontend/src/pages/settings/reminders.tsx`，路由 `/settings/reminders`。頁面 SHALL 為列表，每項含 bill 摘要（銀行 / 期別 / 到期日 / 金額）+ enabled toggle + days_before slider + channel select + 「測試發送」按鈕。

#### Scenario: 列表按到期日排序

- **WHEN** 頁面載入完成
- **THEN** 列表 SHALL 按到期日 ASC（最近到期在最上）

#### Scenario: enabled toggle 樂觀更新

- **WHEN** 使用者 toggle 某 reminder enabled
- **THEN** UI SHALL 立即顯示新狀態、同時送 PUT；API 失敗 SHALL revert + toast

#### Scenario: days_before slider 0-30

- **WHEN** 使用者調整 days_before slider
- **THEN** slider 範圍 SHALL 為 0-30、debounce 500ms 後送 PUT

#### Scenario: channel select 含四選項

- **WHEN** 使用者點 channel select
- **THEN** 選項 SHALL 為 `Telegram`、`UI Banner`、`兩者`、`停用`（對應 enum `telegram` / `ui_banner` / `both` / `none`）

#### Scenario: 測試按鈕回饋

- **WHEN** 使用者點「測試發送」、API 回 `{sent: true}`
- **THEN** 系統 SHALL toast 「測試訊息已發送至 Telegram」（依 channel 文案調整）

### Requirement: scheduler 提醒推送依設定執行

既有 scheduler payment reminder job SHALL 依 `PaymentReminder` 各筆設定執行：`enabled=false` 跳過、`days_before` 決定提前天數、`channel` 決定推送目的地（telegram / ui_banner / both）。`channel="none"` 等同 `enabled=false`。

#### Scenario: enabled=false 不推送

- **WHEN** scheduler 跑 payment reminder job、某 reminder enabled=false
- **THEN** SHALL 不對該 bill 推送任何訊息、log INFO 紀錄已跳過

#### Scenario: channel=both 同時推 Telegram + ui_banner

- **WHEN** scheduler 命中某 reminder.channel="both"
- **THEN** SHALL 同時推 Telegram 訊息與寫入 ui_banner 紀錄；任一失敗不阻斷另一

#### Scenario: ui_banner 紀錄寫入 dashboard 可見資料源

- **WHEN** scheduler 推 ui_banner 提醒
- **THEN** SHALL 寫入既有或新 banner 表（如重用 `budget_alerts` 或新建 `ui_banners` 表）、TTL 1 天、`/api/overview` SHALL 回應含未來 N 天到期 reminder banner 資料給前端
