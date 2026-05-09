## Why

CCAS 終極目標是「**輕鬆部屬本地 + 知道自己信用卡帳務 + 分析 + 管理**」，前三條 change（`compose-pull-deploy`、`pipeline-operations-center`、`oauth-onboarding-ui`）涵蓋了「部屬」與「設定」兩面。但 `frontend/src/pages/{overview,bills,transactions,analytics}.tsx` 截至本 change 啟動前**全為唯讀展示**，使用者每天打開 dashboard 仍只能「看」不能「做」：

- 看到 `STARBUCKS` 被分類成「其他」想改成「餐飲」→ **改不了**（要直接 SQL UPDATE 或重新 train classifier）
- 看到一筆 NT$ 12,000 不知道是什麼 → **無法加備註 / tag**
- 想知道「這個月外食花了多少」相比「上個月」→ Analytics 頁有月趨勢但無類別月對比、無預算超支提示
- 想設「每月外食預算 NT$ 8,000，超出推 Telegram」→ **沒有 UI**（後端有 `PaymentReminder` 模型但只用於繳款提醒）
- 想匯出 2025 全年交易給會計師看 → **沒有匯出按鈕**
- 後端 `classifier/engine.py` 寫死規則，使用者個人化規則（如「`UBER EATS` → 餐飲、不是交通」）只能改 code

換言之：**「分析」目標只達成了基礎（看趨勢圖），「管理」目標完全沒有兌現**。本 change 補上「管理」面向，讓 CCAS 真正成為個人帳務工具，而非「只能看」的 dashboard。

設計重點：本 change **不重構** `classifier/engine.py` 內部演算法，而是引入「使用者自訂規則」DB 表與「手動覆寫」機制，讓使用者個人化決策優先於系統自動分類，符合「個人理財工具」應有的可調性。

## What Changes

- **交易編輯**：新增 `PUT /api/transactions/{id}` 與 `POST /api/transactions/{id}/note` 端點，允許使用者修改 category、note、tags、merchant_alias。Transaction 表新增 `manual_category_override` (bool)、`note` (text)、`tags` (JSON array)、`merchant_alias` (str)、`updated_at` 欄位。Pipeline 重新分類 SHALL **尊重** `manual_category_override=true` 的紀錄，不覆寫使用者手動分類結果。
- **分類規則 UI**：新增 `classification_rules` 表（`id`、`pattern` text、`pattern_type` enum [keyword|regex|exact]、`category_id`、`priority` int、`enabled`、`created_at`、`updated_at`），使用者於 `/settings/rules` 編輯個人規則；分類流程 SHALL 依優先序：(1) `manual_category_override` → (2) `classification_rules`（DB，按 priority desc）→ (3) 既有 `classifier/engine.py` 內建規則 → (4) 預設「未分類」。
- **付款提醒 UI**：暴露既有 `PaymentReminder` 模型至 `/settings/reminders`，含啟用 toggle、提前天數、通知管道（Telegram / 系統內 banner）。
- **預算與警示**：新增 `budgets` 表（`id`、`scope` enum [monthly_total|monthly_category|monthly_bank]、`scope_ref` text [類別 id 或銀行 code]、`amount_minor_units` int、`alert_threshold_percent` int [預設 80]、`enabled`、`created_at`、`updated_at`）。`/settings/budgets` 提供 CRUD UI；scheduler 每日跑 budget evaluation job，超過 threshold 時推 Telegram 與寫入 `budget_alerts` 表（給 dashboard banner 用）。
- **Insights 儀表板 v2**：擴充 `analytics` 路由：
  - `/analytics/compare/banks?year=&month=` — 銀行對比堆疊長條圖
  - `/analytics/compare/years?metric=total|count` — 年度對比折線圖
  - `/analytics/top-merchants?limit=&period=` — 商家排行（依金額 / 筆數）
  - 既有 `/analytics/categories` 增加 `compare_with_previous` 參數（與上月對比百分比）
- **資料匯出**：新增 `GET /api/transactions/export?format=csv|xlsx&start=&end=&bank=&category=` 端點，CSV 走 streaming、Excel 用 `openpyxl`（streaming write）。前端「匯出」按鈕含日期範圍 + 銀行 / 類別 filter。

不在本 change 範圍內：
- **多 user / 共享預算**：仍維持單人單 token 設計。
- **自訂類別樹結構**（如 sub-category）：本 change 沿用既有平層 `Category` 結構。
- **AI / LLM 自動分類建議**：本 change 不引入 LLM dependency 用於分類（既有 Fubon CAPTCHA fallback 用 LLM 為獨立 capability）；rule-based 為主。
- **多幣別**：CCAS 既有設計為新台幣（NT$）為主，本 change 不引入幣別轉換。
- **Web 提醒推送**（service worker push notification）：通知仍走 Telegram + UI banner。

## Capabilities

### New Capabilities

- `transaction-editing`：使用者於 `/transactions/{id}` 詳情頁編輯 category、note、tags、merchant_alias；含 `manual_category_override` 機制保護使用者編輯不被 pipeline 重跑覆寫。
- `classification-rules-management`：使用者於 `/settings/rules` 建立 / 編輯 / 排序個人分類規則（keyword / regex / exact match），規則 SHALL 在 pipeline classify 階段被優先套用。
- `payment-reminders-management`：使用者於 `/settings/reminders` 啟用 / 停用付款提醒，調整提前天數與通知管道；後端既有 `PaymentReminder` 模型暴露為前端 CRUD。
- `budget-and-overspend-alerts`：使用者於 `/settings/budgets` 設定月預算（總額 / 類別 / 銀行），scheduler 每日評估、超過 threshold 推 Telegram 與寫入 banner；dashboard SHALL 顯示當月預算進度條。
- `insights-dashboard-v2`：擴充 analytics 含銀行對比、年度對比、商家排行、月對月百分比變化；資料匯出 CSV / Excel。

### Modified Capabilities

- `pipeline-orchestration`（pipeline-operations-center 既有）：classify 階段 SHALL 套用「`manual_category_override` → `classification_rules` → 既有 engine」優先序，並在 stage_summary 內紀錄各層的命中數，供 UI 揭示。

## Impact

- **新檔案**：
  - 後端：
    - `backend/src/ccas/api/routers/{transactions_edit,rules,reminders_settings,budgets,exports,analytics_v2}.py`
    - `backend/src/ccas/classifier/user_rules.py`（DB 規則匹配引擎）
    - `backend/src/ccas/scheduler/budget_evaluator.py`（每日預算評估 job）
    - `backend/alembic/versions/<ts>_add_user_rules_budgets.py`、`<ts>_add_transaction_user_fields.py`
  - 前端：
    - `frontend/src/pages/transactions/[id].tsx`（編輯頁）
    - `frontend/src/pages/settings/rules.tsx`、`reminders.tsx`、`budgets.tsx`
    - `frontend/src/pages/insights.tsx`（取代或擴充既有 `analytics.tsx`，與既有共存：本 change 把 `/analytics` 重新命名為 `/insights` 以符合本 change 命名）
    - `frontend/src/components/budget-progress-card.tsx`、`comparison-chart.tsx`、`top-merchants-table.tsx`、`export-dialog.tsx`
    - 對應 `*.test.tsx` + `frontend/e2e/{transaction-edit,rules,budgets,insights}.spec.ts`
- **修改**：
  - `backend/src/ccas/storage/models.py`（Transaction 新增欄位、新模型 `ClassificationRule`、`Budget`、`BudgetAlert`）
  - `backend/src/ccas/classifier/engine.py`（注入 user rules 優先邏輯）
  - `backend/src/ccas/api/schemas.py`（新增交易編輯 / 規則 / 預算 / 匯出的 request / response schema）
  - `backend/src/ccas/scheduler/jobs.py`（新增 budget_evaluator daily job 註冊）
  - `frontend/src/pages/transactions.tsx`（每 row 新增「編輯」按鈕、含 inline category 快速改）
  - `frontend/src/pages/overview.tsx`（顯示當月預算進度條 + 超支警示 banner）
  - `frontend/src/components/layout.tsx`（NAV 整合：`Analytics` → `Insights`、`Settings` 子選單擴充）
- **DB 變更**：
  - `transactions` 表新增 5 欄位（`manual_category_override`、`note`、`tags`、`merchant_alias`、`updated_at`）— **加欄位、無破壞性**，既有資料 `manual_category_override` 預設 false。
  - 新增 `classification_rules`、`budgets`、`budget_alerts` 三表。
  - 索引：`classification_rules(priority DESC)`、`budgets(scope, scope_ref)`、`budget_alerts(triggered_at DESC)`。
- **Runtime 依賴**：新增 `openpyxl>=3.1`（Excel 匯出，stream write 模式）；前端可能需 `pnpm dlx shadcn add command popover slider date-range-picker file-trigger`（如未裝）。
- **既有 Analytics 頁面遷移**：本 change 將 `/analytics` 路由 rename 為 `/insights`、舊路由 redirect；既有 `recharts` 圖表組件可重用。
- **Pipeline classify 行為變更**：classify stage 加入「DB user rules」層，可能改變既有交易的分類結果（新規則回溯生效）；`manual_category_override=true` 的紀錄 SHALL 不被覆寫，避免使用者既有手動分類遺失。
- **後續 change 銜接**：無強依賴，可作為終極目標達成的最後一塊；後續 enhancement（多 user、CDSS、AI 分類建議）為獨立工作。
