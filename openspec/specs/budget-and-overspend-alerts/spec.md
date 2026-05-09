# budget-and-overspend-alerts Specification

## Purpose
TBD - created by archiving change bills-management-and-insights. Update Purpose after archive.
## Requirements
### Requirement: budgets 與 budget_alerts 表結構

系統 SHALL 新增 `budgets` 與 `budget_alerts` 兩張資料表。`budgets` 欄位 SHALL 含：`id` UUID PK、`scope` enum (`monthly_total` / `monthly_category` / `monthly_bank`)、`scope_ref` text nullable（依 scope 為 category_id / bank_code）、`amount_minor_units` int（金額以分儲存）、`alert_threshold_percent` int default 80、`enabled` bool default false、`created_at`、`updated_at`。`budget_alerts` 欄位 SHALL 含：`id` UUID PK、`budget_id` FK、`period_year_month` str（如 "2026-05"）、`threshold_breached_percent` int (80 或 100)、`current_amount_minor_units` int、`triggered_at`、`acknowledged_at` nullable。索引：`budgets(scope, scope_ref)`、`budget_alerts(triggered_at DESC)`、`budget_alerts(budget_id, period_year_month)`。

#### Scenario: scope_ref 與 scope 對應

- **WHEN** 建立 `monthly_total` budget
- **THEN** scope_ref SHALL 為 NULL；schema validator SHALL 拒絕 monthly_total 帶 scope_ref 的請求

- **WHEN** 建立 `monthly_category` budget
- **THEN** scope_ref SHALL 為有效 category_id

- **WHEN** 建立 `monthly_bank` budget
- **THEN** scope_ref SHALL 為有效 bank_code（與 banks.yaml 對應）

#### Scenario: amount_minor_units 以分儲存

- **WHEN** 使用者設預算 NT$ 8,000
- **THEN** DB SHALL 存 `amount_minor_units = 800000`（NT$ 1 = 100 分），與既有 transaction.amount_minor_units 慣例一致

### Requirement: GET/POST/PUT/DELETE /api/budgets CRUD

系統 SHALL 提供 budgets CRUD 端點：`GET /api/budgets`（列出，支援 `?scope=` filter）、`POST /api/budgets`（建立）、`PUT /api/budgets/{id}`、`DELETE /api/budgets/{id}`。

#### Scenario: 建立 budget 後立即出現在列表

- **WHEN** `POST /api/budgets` body `{scope: "monthly_total", amount_minor_units: 800000, enabled: true}`
- **THEN** 系統 SHALL INSERT row、回 201、隨後 `GET /api/budgets` 列表 SHALL 含此 row

#### Scenario: scope_ref 驗證

- **WHEN** body `{scope: "monthly_category", scope_ref: "invalid_cat"}` category 不存在
- **THEN** SHALL 回 422、錯誤訊息「scope_ref `invalid_cat` 不是有效的 category_id」

#### Scenario: scope filter

- **WHEN** `GET /api/budgets?scope=monthly_category`
- **THEN** SHALL 僅回 scope=monthly_category 的 budgets

### Requirement: GET /api/budgets/{id}/current-period 當期狀態

系統 SHALL 提供 `GET /api/budgets/{id}/current-period` 端點，回應當月對應 scope 的累計金額與 threshold 狀態。Response 結構 SHALL 為 `{budget_id, period_year_month, amount_used_minor_units, percent_used, threshold_breached: bool, latest_alert?: {...}}`。

#### Scenario: 當月累計依 scope 計算

- **WHEN** budget.scope="monthly_total"、本月已有 transactions 累計 NT$ 6,500
- **THEN** response SHALL 含 `amount_used_minor_units: 650000, percent_used: 81.25, threshold_breached: true`（threshold=80%）

#### Scenario: scope=monthly_category 僅計該類別

- **WHEN** budget.scope="monthly_category", scope_ref="cat_food"
- **THEN** SHALL 僅 SUM transactions WHERE category_id="cat_food" AND month=本月

#### Scenario: scope=monthly_bank 僅計該銀行

- **WHEN** scope="monthly_bank", scope_ref="ctbc"
- **THEN** SHALL 僅 SUM transactions WHERE bank_code="ctbc" AND month=本月

### Requirement: scheduler daily budget evaluation job

系統 SHALL 在 APScheduler 註冊每日 02:00 跑 `evaluate_budgets()` job：對每個 `enabled=true` budget 計算當月對應 scope 的累計金額、與 threshold 比對、必要時觸發 alert（INSERT BudgetAlert + 推 Telegram）。Job SHALL 為冪等：同月同 budget 同 threshold 不重複觸發。

#### Scenario: 80% threshold 觸發 alert

- **WHEN** budget threshold=80, amount=10000、當月累計 8500（85%）、`budget_alerts` 該 budget 該月尚無 80 紀錄
- **THEN** evaluator SHALL INSERT `budget_alerts(threshold_breached_percent=80, current_amount_minor_units=850000)`、推 Telegram「[預算警示] 已使用 85%（NT$ 8,500 / NT$ 10,000）」

#### Scenario: 100% threshold 觸發第二次 alert

- **WHEN** 同 budget 後續累計達 110%、`budget_alerts` 已有 80 紀錄但無 100 紀錄
- **THEN** evaluator SHALL INSERT 新 alert（threshold_breached_percent=100）、推 Telegram「[預算超支] 已超出 10%（NT$ 11,000 / NT$ 10,000）」

#### Scenario: 同月同 threshold 不重複

- **WHEN** evaluator 第二次跑（同日下次 cron）、budget_alerts 該月已有 80 紀錄
- **THEN** SHALL 不重複 INSERT、不重推 Telegram、log INFO「budget #X 80% 已於今月觸發」

#### Scenario: enabled=false 跳過

- **WHEN** budget.enabled=false
- **THEN** evaluator SHALL 跳過該 budget、log INFO

#### Scenario: Telegram disabled 時不 raise

- **WHEN** Telegram bot 未設定 token、evaluator 嘗試推送
- **THEN** SHALL log warning「Telegram disabled，僅寫 BudgetAlert 紀錄」、不 raise；BudgetAlert 仍 INSERT，UI banner 仍可顯示

### Requirement: Telegram 訊息聚合避免噪音

當同日多個 budget 同時超過 threshold（如月底多個類別都超支），evaluator SHALL 將同一日多筆 alert 合併為單則 Telegram 訊息（hourly batch），避免訊息洪流。聚合策略：每小時最多推一次彙總訊息，內容為當前小時內所有新觸發 alert 的摘要列表。

#### Scenario: 同小時 3 個 budget 觸發合併

- **WHEN** 14:00 evaluator 觸發 budget A、B、C 均超 80%
- **THEN** Telegram 推一則訊息含三筆 alert 列表（如「3 個預算超 80%：餐飲 NT$ 8,500/10,000、交通 NT$ 4,200/5,000、購物 NT$ 6,800/8,000」），不推三則獨立訊息

#### Scenario: 跨小時不合併

- **WHEN** 14:00 推一則、15:00 又觸發新 alert
- **THEN** 15:00 SHALL 推獨立訊息（不延後到 16:00 等下一次合併）

### Requirement: GET /api/budgets/alerts/active dashboard banner 資料源

系統 SHALL 提供 `GET /api/budgets/alerts/active` 端點，回當前月份 + 7 天內未確認（`acknowledged_at IS NULL`）的 budget_alerts，給 dashboard banner 顯示用。Response SHALL 為陣列、按 `triggered_at DESC` 排序。

#### Scenario: 未確認 alert 進列表

- **WHEN** 本月有 2 個 alert 未 ack、上月有 1 個 alert 未 ack（已超 7 天）
- **THEN** response SHALL 僅回本月 2 個（上月超過 7 天的不顯示在 dashboard banner）

#### Scenario: acknowledge 後消失

- **WHEN** 使用者 ack 某 alert 後再呼叫此端點
- **THEN** 該 alert SHALL 不出現在回應中、歷史記錄保留（acknowledged_at != null）

### Requirement: POST /api/budgets/alerts/{id}/acknowledge

系統 SHALL 提供 `POST /api/budgets/alerts/{id}/acknowledge` 端點，UPDATE `acknowledged_at = now()`、回 200。已 acknowledged 的 alert 重複 ack SHALL 不報錯（冪等）。

#### Scenario: 冪等 ack

- **WHEN** alert 已 acknowledged、再呼叫 ack
- **THEN** SHALL 回 200、不重複更新 acknowledged_at（保留首次 ack 時間）

### Requirement: /settings/budgets 前端頁面

系統 SHALL 提供 `frontend/src/pages/settings/budgets.tsx`，路由 `/settings/budgets`。頁面 SHALL 列出全部 budgets，每項顯示「當月已用 / 預算 / 進度條（綠 / 黃 / 紅）」。「新增預算」對話框 SHALL 含 scope select、scope_ref（依 scope 顯示 category / bank picker，monthly_total 不顯示）、amount input、threshold slider（50-95，default 80）、enabled toggle。

#### Scenario: 進度條三色階

- **WHEN** budget percent_used = 50%
- **THEN** 進度條 SHALL 顯示綠色

- **WHEN** percent_used = 85%
- **THEN** 進度條 SHALL 顯示黃色

- **WHEN** percent_used = 105%
- **THEN** 進度條 SHALL 顯示紅色 + 「已超支」標籤

#### Scenario: scope_ref 動態欄位

- **WHEN** 對話框中 scope select 改為 monthly_category
- **THEN** scope_ref 欄位 SHALL 切換為 category picker（從 `/api/categories` 載入）

- **WHEN** 改為 monthly_total
- **THEN** scope_ref 欄位 SHALL 隱藏（NULL）

#### Scenario: 編輯既有 budget

- **WHEN** 使用者點某 budget 卡片
- **THEN** 系統 SHALL 開編輯 dialog 預填現有值、提交為 PUT

### Requirement: dashboard 顯示預算超支 banner

`frontend/src/pages/overview.tsx` SHALL 在頁面頂部新增「預算超支警示」banner 區塊，呼叫 `GET /api/budgets/alerts/active`、顯示每個未 ack alert 為一行「[預算超支] {scope_ref 名稱} {percent}% (NT$ {used} / NT$ {budget})」+「我知道了」按鈕。Banner 為 dismissible（ack 後消失）。

#### Scenario: 多個 alert 多行顯示

- **WHEN** 本月有 3 個 alert 未 ack
- **THEN** banner 區塊 SHALL 顯示 3 行、各含對應 budget 摘要與 ack 按鈕

#### Scenario: 點 ack 移除該行

- **WHEN** 使用者點某行「我知道了」
- **THEN** UI SHALL 立即移除該行（樂觀更新）、send `POST /api/budgets/alerts/{id}/acknowledge`、API 失敗時 revert + toast

#### Scenario: 無 active alert 時 banner 區塊隱藏

- **WHEN** active alerts 列表為空
- **THEN** banner 區塊 SHALL 不渲染、不佔頁面空間
