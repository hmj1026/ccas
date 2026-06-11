## MODIFIED Requirements

### Requirement: budgets 與 budget_alerts 表結構

系統 SHALL 新增 `budgets` 與 `budget_alerts` 兩張資料表。`budgets` 欄位 SHALL 含：`id` UUID PK、`scope` enum (`monthly_total` / `monthly_category` / `monthly_bank`)、`scope_ref` text nullable（依 scope 為 category_id / bank_code）、`amount_ntd` int（金額以 NTD 整數元儲存，全系統不做單位換算）、`alert_threshold_percent` int default 80、`enabled` bool default false、`created_at`、`updated_at`。`budget_alerts` 欄位 SHALL 含：`id` UUID PK、`budget_id` FK、`period_year_month` str（如 "2026-05"）、`threshold_breached_percent` int (80 或 100)、`current_amount_ntd` int、`triggered_at`、`acknowledged_at` nullable。索引：`budgets(scope, scope_ref)`、`budget_alerts(triggered_at DESC)`、`budget_alerts(budget_id, period_year_month)`。

#### Scenario: scope_ref 與 scope 對應

- **WHEN** 建立 `monthly_total` budget
- **THEN** scope_ref SHALL 為 NULL；schema validator SHALL 拒絕 monthly_total 帶 scope_ref 的請求

- **WHEN** 建立 `monthly_category` budget
- **THEN** scope_ref SHALL 為有效 category_id

- **WHEN** 建立 `monthly_bank` budget
- **THEN** scope_ref SHALL 為有效 bank_code（與 banks.yaml 對應）

#### Scenario: amount_ntd 以 NTD 整數元儲存

- **WHEN** 使用者設預算 NT$ 8,000
- **THEN** DB SHALL 存 `amount_ntd = 8000`（NTD 整數元，不乘 100），與既有 `transactions.amount` 全系統「整數元」慣例一致

### Requirement: GET/POST/PUT/DELETE /api/budgets CRUD

系統 SHALL 提供 budgets CRUD 端點：`GET /api/budgets`（列出，支援 `?scope=` filter）、`POST /api/budgets`（建立）、`PUT /api/budgets/{id}`、`DELETE /api/budgets/{id}`。

#### Scenario: 建立 budget 後立即出現在列表

- **WHEN** `POST /api/budgets` body `{scope: "monthly_total", amount_ntd: 8000, enabled: true}`
- **THEN** 系統 SHALL INSERT row、回 201、隨後 `GET /api/budgets` 列表 SHALL 含此 row

#### Scenario: scope_ref 驗證

- **WHEN** body `{scope: "monthly_category", scope_ref: "invalid_cat"}` category 不存在
- **THEN** SHALL 回 422、錯誤訊息「scope_ref `invalid_cat` 不是有效的 category_id」

#### Scenario: scope filter

- **WHEN** `GET /api/budgets?scope=monthly_category`
- **THEN** SHALL 僅回 scope=monthly_category 的 budgets

### Requirement: GET /api/budgets/{id}/current-period 當期狀態

系統 SHALL 提供 `GET /api/budgets/{id}/current-period` 端點，回應當月對應 scope 的累計金額與 threshold 狀態。Response 結構 SHALL 為 `{budget_id, period_year_month, amount_ntd, current_amount_ntd, percent, threshold_breached: bool, alert_threshold_percent}`，金額欄位以 NTD 整數元為單位。

#### Scenario: 當月累計依 scope 計算

- **WHEN** budget.scope="monthly_total"、本月已有 transactions 累計 NT$ 6,500
- **THEN** response SHALL 含 `current_amount_ntd: 6500, percent: 81.25, threshold_breached: true`（threshold=80%）

#### Scenario: scope=monthly_category 僅計該類別

- **WHEN** budget.scope="monthly_category", scope_ref="cat_food"
- **THEN** SHALL 僅 SUM transactions WHERE category_id="cat_food" AND month=本月

#### Scenario: scope=monthly_bank 僅計該銀行

- **WHEN** scope="monthly_bank", scope_ref="ctbc"
- **THEN** SHALL 僅 SUM transactions WHERE bank_code="ctbc" AND month=本月

### Requirement: scheduler daily budget evaluation job

系統 SHALL 在 APScheduler 註冊每日 02:00 跑 `evaluate_budgets()` job：對每個 `enabled=true` budget 計算當月對應 scope 的累計金額、與 threshold 比對、必要時觸發 alert（INSERT BudgetAlert + 推 Telegram）。Job SHALL 為冪等：同月同 budget 同 threshold 不重複觸發。

#### Scenario: 80% threshold 觸發 alert

- **WHEN** budget threshold=80, amount_ntd=10000、當月累計 8500（85%）、`budget_alerts` 該 budget 該月尚無 80 紀錄
- **THEN** evaluator SHALL INSERT `budget_alerts(threshold_breached_percent=80, current_amount_ntd=8500)`、推 Telegram「[預算警示] 已使用 85%（NT$ 8,500 / NT$ 10,000）」

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
