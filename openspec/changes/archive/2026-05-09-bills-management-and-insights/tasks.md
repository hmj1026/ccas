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

- [x] 3.1 建立 `backend/src/ccas/api/routers/transactions_edit.py`（含 GET 詳情 + PUT/POST/DELETE 編輯共 4 端點）
- [x] 3.2 實作 `PUT /api/transactions/{id}`：body `{category_id?, note?, tags?, merchant_alias?}`，更新對應欄位（`updated_at` 由 SQLAlchemy `onupdate=_utcnow` + SQLite trigger 雙保險自動寫入）、若改 category_id 同步設 `manual_category_override = true`；invalid category_id → 422
- [x] 3.3 實作 `POST /api/transactions/{id}/note`：body `{note: str}`，僅更新 note 欄位（不影響 manual_override）
- [x] 3.4 實作 `DELETE /api/transactions/{id}/manual-override`：清除 manual_override flag + 即時跑 `user_rules → engine` classify（**spec deviation**：採「即時」路徑，與 pipeline `run_classify_job` 邏輯共用）
- [x] 3.5 為四個端點寫 router 整合測試（17 案：CRUD happy path + 404 + 422 + auth + GET detail + 多欄位部分更新 + reclassify behavior）
- [x] 3.6 為 manual_override 機制寫端對端測試：編輯 category → 連跑 5 次 `run_classify_job` → category 保留為使用者編輯值；同步把 `run_reclassify_job` 改為遵守 `manual_override → user_rules → engine` 優先序（§15.1 acceptance）

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

- [x] 5.1 建立 `backend/src/ccas/api/routers/reminders_settings.py`（**spec deviation**：design §D9 假設既有 PaymentReminder 含 `(days_before, channel, enabled)`，實際只有 `(bill_id, reminder_type, sent_at)` sent log；故獨立新表 `reminder_settings` 儲存設定，PaymentReminder 不動。新增 alembic migration `9b3e2c8a4f10_add_reminder_settings.py`）
- [x] 5.2 實作 `GET /api/reminders/settings`：列出全部「未付帳單」與其設定（settings 缺席時回預設 `enabled=true / days_before=[3,1] / channel=telegram`，與 change 前 scheduler 行為等價）
- [x] 5.3 實作 `PUT /api/reminders/{bill_id}/settings`：partial upsert；驗證 days_before 元素為正整數
- [x] 5.4 實作 `POST /api/reminders/{bill_id}/test`：依 channel 路由（telegram/both → send_message；ui_banner → 不外送回提示）
- [x] 5.5 為三個端點寫 router 整合測試（11 案：list 三路徑 + update CRUD + 404/422/auth + test push 三 channel）

## 6. 後端：預算 API + scheduler job

- [x] 6.1 建立 `backend/src/ccas/api/routers/budgets.py`
- [x] 6.2 實作 `GET /api/budgets`：列出全部 budgets，可選 `?scope=` filter
- [x] 6.3 實作 `POST /api/budgets`：scope_ref 一致性驗證（monthly_total 拒絕 scope_ref；monthly_category 驗 categories.category；monthly_bank 驗 bank_configs.bank_code）
- [x] 6.4 實作 `PUT /api/budgets/{id}` 與 `DELETE /api/budgets/{id}`（partial update + scope/scope_ref 改動 re-validate + 404）
- [x] 6.5 實作 `GET /api/budgets/{id}/current-period`：當月累計 + percent + threshold_breached
- [x] 6.6 建立 `backend/src/ccas/scheduler/budget_evaluator.py`：`evaluate_budgets()` 兩階 threshold ladder（configured + 100%）+ INSERT BudgetAlert + 聚合 Telegram 推送
- [x] 6.7 `scheduler/jobs.py` 新增 `run_budget_evaluator_sync` + `__main__.py` 註冊每日 02:00 cron job（含 unit test 覆蓋 cron schedule）
- [x] 6.8 evaluator 以 `(budget_id, period_year_month, threshold)` 既存查詢去重；同月同 threshold 不重複觸發
- [x] 6.9 Telegram 訊息聚合：每次 evaluator run 內所有新增 alert 合併為單則訊息（單元測試 `test_aggregates_multiple_alerts_into_single_message` 覆蓋）
- [x] 6.10 evaluator 整合測試 6 案：80% / 100%（更高階再觸發）/ 不重複 / disabled / Telegram disabled 不 raise / 多 budget 聚合
- [x] 6.11 實作 `GET /api/budgets/alerts/active`：未確認且當月 alert（含 budget meta）
- [x] 6.12 實作 `POST /api/budgets/alerts/{id}/acknowledge`：UPDATE acknowledged_at = utcnow()

## 7. 後端：Insights API（analytics v2）

- [x] 7.1 建立 `backend/src/ccas/api/routers/analytics_v2.py`（與既有 `analytics.py` 並存）
- [x] 7.2 實作 `GET /api/analytics/compare/banks?year=&month=`：JOIN transactions GROUP BY bank_code
- [x] 7.3 實作 `GET /api/analytics/compare/years?metric=total|count`：依 metric 切換 SUM / COUNT 聚合
- [x] 7.4 實作 `GET /api/analytics/top-merchants?limit=&period=year|month|all&offset_months=`：GROUP BY merchant DESC by total
- [x] 7.5 修改既有 `GET /api/analytics/categories`：新增 `?compare_with_previous=true`（搭配 `month` 必填）回上月對比 + change_percent；維持 backward compatibility（不帶旗標時保留 CategoryItem schema）
- [x] 7.6 整合測試 8 案：banks 空 / 單月分組、years total / count、top-merchants 限額排序 + 空、categories 比較模式 + legacy 模式

## 8. 後端：CSV / Excel 匯出 API

- [x] 8.1 建立 `backend/src/ccas/api/routers/exports.py`（**spec deviation**：`transactions.py` 既有 legacy CSV export 已移除，避開 `/api/transactions/{id}` 動態 segment 衝突，並在 app.py 將 exports.router 註冊於 transactions_edit 之前）
- [x] 8.2 實作 `GET /api/transactions/export?format=csv`：`session.stream()` + `csv.writer` 逐筆 yield bytes，support start/end/bank/category filter
- [x] 8.3 實作 `GET /api/transactions/export?format=xlsx`：`openpyxl.Workbook(write_only=True)` + tempfile + chunked StreamingResponse；自動 cleanup tempfile
- [x] 8.4 在 pyproject.toml 主依賴中新增 `openpyxl>=3.1`（**spec deviation**：spec 指 `[optional-dependencies] api`，但專案目前無 `api` extras 群組；放主依賴與既有 fastapi/sqlalchemy 同層級）
- [x] 8.5 整合測試 9 案：空資料、unicode 商家、日期 / 銀行 / 類別 filter、include_user_fields 欄位齊全、xlsx 含 user fields、不接受 format=pdf
- [x] 8.6 大量資料測試：`test_exports_streaming_benchmark.py` 驗證 5K 預設 / 50K（`CCAS_BENCH_50K=1`）兩種規模下 CSV streaming row count + latency + tracemalloc peak < 50/100MB；xlsx 走 write_only + tempfile path

## 9. 前端：交易編輯頁

- [x] 9.1 建立 `frontend/src/pages/transaction-detail.tsx`（**spec deviation**：react-router 7 使用 `:id` 路由 segment 而非 Next.js 風格的 `[id].tsx`；route 在 `App.tsx` 註冊為 `transactions/:id`）
- [x] 9.2 category select：從 `/api/settings/categories` 取列表、改後立刻 PUT，react-query setQueryData 樂觀更新
- [x] 9.3 note textarea：debounce 500ms 自動儲存、`onBlur` 立即 flush
- [x] 9.4 tags input：chip 顯示 + Enter 新增、X 移除，每次操作即送 PUT
- [x] 9.5 merchant_alias input：text field with 500ms debounce
- [x] 9.6 「分類來源」徽章：`manual_override` / `auto`（user_rule + engine 兩者皆顯示為 auto，徽章上含 hover tooltip 解釋；user_rule 細分仍可由後端 `pattern` 判讀，UI v1 暫合併以降低噪音）
- [x] 9.7 「重置覆寫」按鈕：呼叫 `DELETE /api/transactions/{id}/manual-override`
- [x] 9.8 Vitest 8 案：渲染 / 改 category PUT / debounce note 單次 PUT / manual override 顯示 / DELETE / 新增 tag / PUT 失敗顯示錯誤訊息 / 無效 ID 顯示
- [x] 9.9 修改 `frontend/src/pages/transactions.tsx`：每 row 加 Pencil 按鈕跳到 `/transactions/{id}`（**spec deviation**：inline 表格 quick-change 留待 v2，避免列表頁邏輯複雜化）
- [x] 9.10 e2e `frontend/e2e/transaction-edit.spec.ts`：3 個情境（列表→詳情→改 category→reload 保留 / 重置覆寫 / 新增 tag）

## 10. 前端：分類規則 UI

- [x] 10.1 建立 `frontend/src/pages/settings-rules.tsx`（**spec deviation**：路徑為 `/settings/rules`，檔案在 `pages/settings-rules.tsx`，與 reminders/budgets 同層命名）— 表格欄位 pattern / 類型 / 類別 / priority / 啟用 toggle / 刪除
- [x] 10.2 `RuleDialog` 元件：pattern_type / pattern / category（去重 from `/api/settings/categories`）/ priority + 內建 fieldset「測試規則」即時 POST `/api/rules/test`，UI 顯示 ✓ 命中 / ✗ 未命中
- [x] 10.3 priority 直覺調整（**spec deviation**：採 inline `<input type=number>` + 500ms debounce PUT，列表回流即依新 priority 重新排序；真正 drag-and-drop 留待 v2，避免引入 dnd lib 拉大 PR 範圍）
- [x] 10.4 `detectComplexRegex` 偵測 `(.+)+` / `(.*)*` 等 nested quantifier，pattern_type=regex 時於 dialog 顯示 amber `<div role=alert>` 警告 banner
- [x] 10.5 `pages/__tests__/settings-rules.test.tsx` 8 案：empty / 列表 / toggle PUT / priority debounce PUT / delete + confirm / regex warning / test mutation / create POST + dialog 收起
- [x] 10.6 `frontend/e2e/rules.spec.ts` 3 情境：NAV「分類規則」進入 + toggle / dialog 即時 test + 建立 / regex nested quantifier 警示（**spec deviation**：「跑 pipeline → 該規則套用」由 backend `tests/integration/classifier/test_classify_priority.py` §15.2 覆蓋，前端 e2e 聚焦 UI mutation 路徑）

## 11. 前端：付款提醒 UI

- [x] 11.1 建立 `frontend/src/pages/settings-reminders.tsx`（**spec deviation**：路徑為 `/settings/reminders` 但檔案在 `pages/settings-reminders.tsx`，與既有命名一致）— 列出所有未付帳單含 enabled toggle / days_before（逗號 input on blur commit）/ channel select
- [x] 11.2 「測試發送」按鈕：呼叫 `POST /api/reminders/{bill_id}/test`、行內顯示 detail（telegram 顯示 ✓ 已送出、ui_banner 顯示 detail）
- [x] 11.3 為頁面寫 Vitest（6 案：empty / list / toggle enabled / channel change / test push / days parse-on-blur）

## 12. 前端：預算 UI

- [x] 12.1 建立 `frontend/src/pages/settings-budgets.tsx`：列出全部 budgets + 每筆 BudgetProgressCard
- [x] 12.2 「新增預算」對話框：scope select / scope_ref text input（monthly_total 隱藏）/ amount number input / threshold slider；含本地 validation
- [x] 12.3 budget 卡片顯示「當月已花 / 預算 / 百分比」進度條（綠 < 80 / 黃 80-100 / 紅 ≥ 100）
- [x] 12.4 修改 `frontend/src/pages/overview.tsx`：頁面頂部新增 `<BudgetAlertBanner>`（呼叫 `/api/budgets/alerts/active`、含 acknowledge 按鈕；無 alert 不渲染）
- [x] 12.5 建立 `frontend/src/components/budget-progress-card.tsx` 組件 + `budget-alert-banner.tsx`（拆分 banner 元件以保持 overview 簡潔）
- [x] 12.6 為頁面與組件寫 Vitest（6 案：empty / 渲染進度 / 建立預算 / monthly_category 缺 scope_ref 拒絕 / 刪除 / toggle enabled）
- [ ] 12.7 e2e `budgets.spec.ts`（PR-D4 §15 集中跑 e2e；本 PR 僅 Vitest 覆蓋）

## 13. 前端：Insights 頁

- [x] 13.1 建立 `frontend/src/pages/insights.tsx`；舊 `analytics.tsx` 已刪除，`/analytics` 路由 redirect 到 `/insights`
- [x] 13.2 月趨勢區塊（含 trend_months select 6/12/24）＋ 「類別 vs 上月」區塊（when month set）顯示 ▲/▼ 百分比
- [x] 13.3 銀行對比長條圖（`BankComparisonBarChart` 使用 recharts BarChart）
- [x] 13.4 年度對比折線圖（`YearComparisonLineChart`，metric=total/count 切換）
- [x] 13.5 商家排行表格（`TopMerchantsTable`，含 limit 5/10/20、period all/month/year 切換）
- [x] 13.6 「匯出」按鈕：開啟 `ExportDialog`（format / 日期 / 銀行 / 類別 / include_user_fields）→ apiFetchBlob → URL.createObjectURL 觸發下載
- [x] 13.7 建立 `frontend/src/components/{comparison-chart,top-merchants-table,export-dialog}.tsx`
- [x] 13.8 Vitest 4 案：渲染所有區塊 / 切換 metric → 重新 fetch / month 設定時顯示 compare 區塊 / export dialog blob 下載
- [x] 13.9 NAV「分析」改為「Insights」、icon 換 `Sparkles`；App.test.tsx 同步更新
- [x] 13.10 e2e `insights.spec.ts`：4 個情境（NAV → 主要區塊 / 切換 year_metric / month query 顯示 compare / export dialog blob 下載）

## 14. Docs

- [x] 14.1 撰寫 `docs/personal-rules-and-budgets.md`：完整使用者操作流程、規則 best practice、預算設定範例、regex 入門
- [x] 14.2 修改 `docs/install-quickstart.md`：在 onboarding 步驟之後新增「步驟 7：個人化設定」段落，連結到 reminders/budgets/insights 三個子頁與 personal-rules-and-budgets.md
- [x] 14.3 README 加入「個人帳務管理」段落，列出本 change 提供的能力

## 15. 端對端驗證

- [x] 15.1 編輯保留測試：`tests/integration/test_transactions_edit.py` 中 `run_classify_job` × 5 次後 manual_override 保留（§3.6 同步）
- [x] 15.2 規則優先序測試：`tests/integration/classifier/test_classify_priority.py` 5 案 — manual_override skip / user_rules 高 priority 勝出 / engine fallback / default category / 混合 mix
- [x] 15.3 規則 timeout 測試：`tests/integration/classifier/test_user_rules.py::test_regex_timeout_logs_warning_and_continues`
- [x] 15.4 預算超支測試：`tests/integration/test_budget_evaluator.py` 80% / 100% threshold ladder + Telegram 訊息聚合；banner active alert + acknowledge 由 `test_budgets_router.py` 覆蓋
- [x] 15.5 預算冪等測試：`test_budget_evaluator.py::test_does_not_duplicate_alert_for_same_month_threshold`
- [x] 15.6 Insights 大量資料測試：`tests/integration/test_exports_streaming_benchmark.py` 5K 基線（CI）+ `CCAS_BENCH_50K=1` 50K acceptance；CSV latency budget 8s / 30s
- [x] 15.7 匯出 streaming 測試：同上檔案；tracemalloc 確認 CSV peak < 50MB（5K）/ 100MB（50K），xlsx 走 write_only + tempfile 不 OOM
- [x] 15.8 NAV 整合測試：`frontend/e2e/insights.spec.ts` 涵蓋 NAV「Insights」進入；reminders/budgets 入口由 `App.test.tsx` 與 layout vitest 覆蓋
- [x] 15.9 升級相容性：alembic migration `a4b8c2d6e0f1_add_transaction_user_fields.py` 5 欄位 default false / [] / null，§1.7 冪等測試已過

## 16. OpenSpec 收尾

- [x] 16.1 `openspec validate bills-management-and-insights --strict` 通過
- [x] 16.2 確認本 change 落地順序：與 `oauth-onboarding-ui` 程式碼正交可平行；本 change 已在 oauth-onboarding-ui 後實作，沿用「設定中心」NAV
- [x] 16.3 完成後 `/opsx:archive bills-management-and-insights`，確認 delta 同步至 `openspec/specs/`
