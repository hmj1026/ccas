## 1. DB 模型與 migration

- [x] 1.1 在 `backend/src/ccas/storage/models.py` `Transaction` 新增 5 欄位（**spec deviation**：note 已存在保留 nullable Text；其餘四欄位新增）
- [x] 1.2 新增 `ClassificationRule` 模型（**spec deviation**：Python class 改名 `UserClassificationRule` 避開既有 `classifier/rules.py:ClassificationRule` dataclass；table 名仍為 `classification_rules`）
- [x] 1.3 新增 `Budget` 模型（`id` PK、`scope` enum、`scope_ref` text nullable、`amount_minor_units` int、`alert_threshold_percent` int default 80、`enabled` bool、`created_at`、`updated_at`）
- [x] 1.4 新增 `BudgetAlert` 模型（`id` PK、`budget_id` FK、`period_year_month` str、`threshold_breached_percent` int、`current_amount_minor_units` int、`triggered_at`、`acknowledged_at` nullable）
- [x] 1.5 建立 alembic migration `a4b8c2d6e0f1_add_transaction_user_fields.py`（**spec deviation**：索引改為 `(category, trans_date)` — 既有 schema 無 category_id FK，等價支援 insights group by）
- [x] 1.6 建立 alembic migration `5f9d4a7b3c8e_add_user_rules_budgets.py`：3 表 + 全部 spec 索引 + SQLite updated_at triggers
- [x] 1.7 兩 migration 都驗證 `upgrade head` + `downgrade -2` + `upgrade head` 冪等

## 2. 後端：分類規則引擎

- [x] 2.1 建立 `backend/src/ccas/classifier/user_rules.py`：`UserRuleMatcher` 含 100ms timeout via `asyncio.wait_for(loop.run_in_executor(...))`
- [x] 2.2 為三種 pattern_type 寫單元測試：keyword / exact / regex 各覆蓋 happy path + edge case
- [x] 2.3 為 regex timeout 寫測試（monkeypatch `_re_search` 模擬慢）→ 觸發 timeout、log warning、不阻斷其他規則
- [x] 2.4 修改 `backend/src/ccas/classifier/job.py`（**spec deviation**：spec 寫修改 `engine.py`，實際在 job.py 編排優先序保持 engine 純函式不動）
- [x] 2.5 為新優先序寫整合測試 5 案：manual_override skip / user_rules win / engine fallback / default category / 混合 mix breakdown
- [ ] 2.6 在 stage_summary 內紀錄各層命中數（**partial**：ClassifySummary 已含欄位 + logger.info 輸出；尚未串接到 PipelineRun.stage_summary[-1] 額外 key — 需擴展 ProgressReporter.stage_finished 契約，留下個 PR 補）

## 3. 後端：交易編輯 API

- [ ] 3.1 建立 `backend/src/ccas/api/routers/transactions_edit.py`
- [ ] 3.2 實作 `PUT /api/transactions/{id}`：body `{category_id?, note?, tags?, merchant_alias?}`，更新對應欄位、設 `updated_at = now()`、若改 category_id 同步設 `manual_category_override = true`
- [ ] 3.3 實作 `POST /api/transactions/{id}/note`：body `{note: str}`，僅更新 note 欄位（簡化常用操作）
- [ ] 3.4 實作 `DELETE /api/transactions/{id}/manual-override`：清除 manual_category_override + 重新走 classify 邏輯（即時或標記下次 pipeline 處理）
- [ ] 3.5 為三個端點寫 router 整合測試：覆蓋成功 / 404 / 422
- [ ] 3.6 為 manual_override 機制寫端對端測試：編輯 category → 重跑 pipeline → 該筆 category 保留、stage_summary 記錄 skipped_due_to_manual_override

## 4. 後端：分類規則 API

- [x] 4.1 建立 `backend/src/ccas/api/routers/rules.py`
- [x] 4.2 實作 `GET /api/rules`：列出全部 rules、按 priority DESC + id ASC，支援 `?enabled=true|false` filter
- [x] 4.3 實作 `POST /api/rules`：body `{pattern, pattern_type, category_id, priority?, enabled?}`；invalid category_id → 422
- [x] 4.4 實作 `PUT /api/rules/{id}`：partial update；不存在 → 404
- [x] 4.5 實作 `DELETE /api/rules/{id}`：不存在 → 404
- [x] 4.6 實作 `POST /api/rules/test`：重用 UserRuleMatcher（含 100ms regex timeout fail-soft）保證與 pipeline 行為一致
- [x] 4.7 為五個端點寫 router 整合測試（17 案：CRUD happy path + 404 + 422 + auth + regex compile error fail-soft）
- [x] 4.8 為 priority 排序與 enabled filter 寫測試覆蓋

## 5. 後端：付款提醒 API

- [ ] 5.1 建立 `backend/src/ccas/api/routers/reminders_settings.py`（既有 `reminders.py` 為 readonly 列表，本 change 補 settings CRUD）
- [ ] 5.2 實作 `GET /api/reminders/settings`：列出全部 reminders 與其設定
- [ ] 5.3 實作 `PUT /api/reminders/{bill_id}/settings`：body `{enabled?, days_before?, channel?}`
- [ ] 5.4 實作 `POST /api/reminders/{bill_id}/test`：立即推送一次測試訊息（給 channel）
- [ ] 5.5 為三個端點寫 router 整合測試

## 6. 後端：預算 API + scheduler job

- [ ] 6.1 建立 `backend/src/ccas/api/routers/budgets.py`
- [ ] 6.2 實作 `GET /api/budgets`：列出全部 budgets，可選 `?scope=` filter
- [ ] 6.3 實作 `POST /api/budgets`：body `{scope, scope_ref?, amount_minor_units, alert_threshold_percent?, enabled?}`、建立 budget；驗證 scope_ref 與 scope 一致（monthly_total 不得有 scope_ref；monthly_category 必須有 valid category_id；monthly_bank 必須有 valid bank_code）
- [ ] 6.4 實作 `PUT /api/budgets/{id}` 與 `DELETE /api/budgets/{id}`
- [ ] 6.5 實作 `GET /api/budgets/{id}/current-period`：回當月對應 scope 的累計金額 + threshold 狀態
- [ ] 6.6 建立 `backend/src/ccas/scheduler/budget_evaluator.py`：`evaluate_budgets()` 函式遍歷 enabled budgets、計算當月累計、超 threshold 觸發 alert（INSERT BudgetAlert + 推 Telegram）
- [ ] 6.7 在 `backend/src/ccas/scheduler/jobs.py` 註冊每日 02:00 跑 `evaluate_budgets()`
- [ ] 6.8 evaluator 加入「同月同 budget 同 threshold 不重複觸發」邏輯（query budget_alerts 已存在判斷）
- [ ] 6.9 Telegram 訊息聚合：同日多預算超支合併為單則訊息（hourly batch）；單元測試覆蓋
- [ ] 6.10 為 evaluator 寫整合測試：(a) 80% threshold 觸發、(b) 100% threshold 觸發、(c) 已觸發不重複、(d) enabled=false 不觸發、(e) Telegram disabled 時不 raise
- [ ] 6.11 實作 `GET /api/budgets/alerts/active`：回當前月份 + 7 天內未確認 alert，給 dashboard banner 用
- [ ] 6.12 實作 `POST /api/budgets/alerts/{id}/acknowledge`：UPDATE acknowledged_at = now()

## 7. 後端：Insights API（analytics v2）

- [ ] 7.1 建立 `backend/src/ccas/api/routers/analytics_v2.py`（與既有 `analytics.py` 並存，本 change 後者部分 endpoint 標 deprecated）
- [ ] 7.2 實作 `GET /api/analytics/compare/banks?year=&month=`：GROUP BY bank_code 回每銀行金額
- [ ] 7.3 實作 `GET /api/analytics/compare/years?metric=total|count`：GROUP BY year 回每年金額或筆數
- [ ] 7.4 實作 `GET /api/analytics/top-merchants?limit=&period=year|month&offset_months=`：GROUP BY description 取 top N
- [ ] 7.5 修改既有 `GET /api/analytics/categories`：新增 `?compare_with_previous=true` 回上月對比百分比
- [ ] 7.6 為四個 endpoint 寫整合測試（覆蓋空資料、單月、跨年）

## 8. 後端：CSV / Excel 匯出 API

- [ ] 8.1 建立 `backend/src/ccas/api/routers/exports.py`
- [ ] 8.2 實作 `GET /api/transactions/export?format=csv&start=&end=&bank=&category=&include_user_fields=`：StreamingResponse + `csv.writer`，逐筆 yield；支援日期 / 銀行 / 類別 filter
- [ ] 8.3 實作 `GET /api/transactions/export?format=xlsx&...`：用 `openpyxl.Workbook(write_only=True)`、tempfile + StreamingResponse
- [ ] 8.4 在 pyproject.toml `[project.optional-dependencies] api` 顯式新增 `openpyxl>=3.1`
- [ ] 8.5 為兩種格式寫整合測試：覆蓋空資料、含 unicode 商家名、include_user_fields=true 時欄位齊全
- [ ] 8.6 大量資料測試：mock 50K 筆 transactions、驗證 streaming 不 OOM（peak memory < 100MB）

## 9. 前端：交易編輯頁

- [ ] 9.1 建立 `frontend/src/pages/transactions/[id].tsx`：詳情頁含 inline edit
- [ ] 9.2 category select：從 `/api/categories` 取列表、改後立刻 PUT、樂觀更新
- [ ] 9.3 note textarea：debounce 500ms 自動儲存、最後一次焦點失去時 flush
- [ ] 9.4 tags input：multi-select chip、新增 / 移除即送 PUT
- [ ] 9.5 merchant_alias input：簡單 text field
- [ ] 9.6 顯示「分類來源」徽章：manual_override / user_rule#N / engine / 預設，含 hover tooltip 解釋
- [ ] 9.7 「重置覆寫」按鈕：呼叫 `DELETE /api/transactions/{id}/manual-override`
- [ ] 9.8 為頁面寫 Vitest：覆蓋編輯 / debounce / 樂觀更新 / 失敗 revert
- [ ] 9.9 修改 `frontend/src/pages/transactions.tsx`：每 row 加「編輯」按鈕跳到詳情頁；加 inline category quick-change（直接在表格中改 category）
- [ ] 9.10 e2e `transaction-edit.spec.ts`：列表 → 編輯 → 改 category → 重整保留 → 重跑 pipeline 不被覆寫

## 10. 前端：分類規則 UI

- [ ] 10.1 建立 `frontend/src/pages/settings/rules.tsx`：表格（pattern / type / category / priority / enabled toggle / 操作）
- [ ] 10.2 「新增規則」對話框：pattern input + type select + category select + priority + 「測試規則」區塊（即時呼叫 `/api/rules/test`）
- [ ] 10.3 拖拉排序 priority：UI 直觀調整 priority 欄位
- [ ] 10.4 「複雜度警示」：regex pattern 含 nested quantifier 時顯示警告 banner
- [ ] 10.5 為頁面寫 Vitest：CRUD 流程、測試規則 mutation
- [ ] 10.6 e2e `rules.spec.ts`：建立規則 → 跑 pipeline → 該規則正確套用

## 11. 前端：付款提醒 UI

- [ ] 11.1 建立 `frontend/src/pages/settings/reminders.tsx`：列出所有 PaymentReminder 含 enabled toggle / days_before / channel select
- [ ] 11.2 「測試發送」按鈕：呼叫 `POST /api/reminders/{bill_id}/test`、toast 顯示成功 / 失敗
- [ ] 11.3 為頁面寫 Vitest

## 12. 前端：預算 UI

- [ ] 12.1 建立 `frontend/src/pages/settings/budgets.tsx`：列出全部 budgets + 當月進度條
- [ ] 12.2 「新增預算」對話框：scope select、scope_ref（依 scope 顯示 category / bank picker）、amount input、threshold slider
- [ ] 12.3 budget 卡片顯示「當月已花 / 預算 / 百分比」進度條（綠 / 黃 / 紅 三色階）
- [ ] 12.4 修改 `frontend/src/pages/overview.tsx`：頁面頂部新增「預算超支警示」banner（呼叫 `/api/budgets/alerts/active`）、含 acknowledge 按鈕
- [ ] 12.5 建立 `frontend/src/components/budget-progress-card.tsx` 組件
- [ ] 12.6 為頁面與組件寫 Vitest
- [ ] 12.7 e2e `budgets.spec.ts`：建立 80% threshold 預算 → mock 超支 → 驗證 banner 顯示 → acknowledge → banner 消失

## 13. 前端：Insights 頁

- [ ] 13.1 建立 `frontend/src/pages/insights.tsx`（取代既有 `analytics.tsx`，後者改為 redirect 到 `/insights`）
- [ ] 13.2 月趨勢區塊（既有），補上「月對月變化百分比」
- [ ] 13.3 銀行對比堆疊長條圖：呼叫 `/api/analytics/compare/banks`、用 recharts BarChart
- [ ] 13.4 年度對比折線圖：呼叫 `/api/analytics/compare/years`、recharts LineChart
- [ ] 13.5 商家排行表格：呼叫 `/api/analytics/top-merchants`、含 limit / period select
- [ ] 13.6 「匯出」按鈕：開啟 `<ExportDialog>`（日期範圍 + 銀行 / 類別 filter + format select + include_user_fields toggle）→ 觸發下載
- [ ] 13.7 建立 `frontend/src/components/{comparison-chart,top-merchants-table,export-dialog}.tsx`
- [ ] 13.8 為頁面與組件寫 Vitest
- [ ] 13.9 修改 `frontend/src/components/layout.tsx`：NAV「Analytics」改為「Insights」、icon 換 `BarChart3` 或 `Sparkles`
- [ ] 13.10 e2e `insights.spec.ts`：頁面載入 → 切換 compare 模式 → 匯出 CSV → 下載成功

## 14. Docs

- [ ] 14.1 撰寫 `docs/personal-rules-and-budgets.md`：完整使用者操作流程、規則 best practice、預算設定範例、regex 入門
- [ ] 14.2 修改 `docs/install-quickstart.md`：在「進入 dashboard」步驟之後新增「個人化設定」段落，連結到三個 settings 子頁與 insights
- [ ] 14.3 README 加入「個人帳務管理」段落，列出本 change 提供的能力

## 15. 端對端驗證

- [ ] 15.1 編輯保留測試：手動改 category → 重跑 pipeline 5 次 → category 不變、stage_summary 含 skipped_due_to_manual_override 計數
- [ ] 15.2 規則優先序測試：建立 rule（priority=10）+ 內建 engine 也能匹配同 description → classify 結果為 rule 指定 category
- [ ] 15.3 規則 timeout 測試：建立惡意 regex pattern → 驗證 100ms 超時 + log warning + 後續 transactions 仍能 classify
- [ ] 15.4 預算超支測試：建立 monthly_total budget=10000、threshold=80 → 累計 8500 → evaluator 跑 → Telegram 收到訊息 + banner 出現 → acknowledge 後 banner 消失
- [ ] 15.5 預算冪等測試：同月觸發後再跑 evaluator → 不重複推 Telegram、不新增 BudgetAlert
- [ ] 15.6 Insights 大量資料測試：模擬 50K 筆 transactions（5 年）→ /insights 載入時間 < 3s、banks 對比 query < 500ms
- [ ] 15.7 匯出 streaming 測試：匯出 50K 筆 → response 為 chunked、backend peak memory < 100MB
- [ ] 15.8 NAV 整合測試：「Insights」與「設定中心 > rules / reminders / budgets」navigation 路徑正確
- [ ] 15.9 升級相容性：既有 transactions（無 manual_category_override 欄位）alembic upgrade 後預設 false、行為無變化

## 16. OpenSpec 收尾

- [ ] 16.1 `openspec validate bills-management-and-insights --strict` 通過
- [ ] 16.2 確認本 change 落地順序：與 `oauth-onboarding-ui` 程式碼正交可平行，但建議在 `oauth-onboarding-ui` 後啟動實作（為「設定中心」NAV 結構需要）
- [ ] 16.3 完成後 `/opsx:archive bills-management-and-insights`，確認 delta 同步至 `openspec/specs/`
