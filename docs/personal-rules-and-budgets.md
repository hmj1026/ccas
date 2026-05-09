# 個人帳務管理：交易編輯、規則、預算與 Insights

CCAS 在 `bills-management-and-insights` change 之後支援以下個人帳務操作：

- **交易編輯**：手動覆寫類別、新增備註 / 標籤 / 商家別名
- **個人分類規則**：以 keyword / exact / regex 三種 pattern 對交易自動套類別，優先序高於內建 engine
- **付款提醒**：未付帳單可逐筆設定 `enabled / days_before / channel`
- **預算告警**：每月總額 / 單一類別 / 單一銀行三種 scope，超過閾值由 Telegram 推播
- **Insights**：銀行對比、年度對比、商家排行、類別月對月變化
- **匯出**：CSV / xlsx 兩種格式，支援日期 / 銀行 / 類別 filter

> 路徑前綴假設為 dashboard 預設 `http://localhost:8080`。

---

## 1. 交易編輯（手動覆寫）

### 進入方式

1. 開啟 `/transactions`，找到目標交易
2. 點 row 右側的鉛筆 icon → 進入 `/transactions/{id}` 詳情頁

### 可編輯欄位

| 欄位 | 行為 |
|---|---|
| 類別（select）| 選擇後立即 `PUT`，自動將 `manual_category_override` 設為 `true` |
| 備註（textarea）| 500ms debounce 自動儲存；`onBlur` 立即 flush |
| 標籤（chip + Enter）| 每次新增 / 移除即送 `PUT` |
| 商家別名（input）| 500ms debounce 自動儲存 |

### 「分類來源」徽章

- **手動覆寫**：使用者顯式改過 → 重跑 pipeline 不會被覆蓋
- **自動分類**：由規則或內建 engine 推得

點「重置覆寫」按鈕會清除 flag 並即時跑 `user_rules → engine → 預設` 重新分類。

### 為什麼 manual override 不被 pipeline 覆寫

`run_classify_job` 與 `run_reclassify_job` 都遵守以下優先序：

```
manual_override（保留）→ user_rules → engine → 預設
```

`stage_summary` 包含 `skipped_due_to_manual_override` 計數，可在 `/operations` 觀察。

---

## 2. 個人分類規則

進入 `/settings/rules`：表格列出全部規則（priority DESC + id ASC），可 inline 切換 enabled、debounced 編輯 priority、刪除（含確認），右上「新增規則」開啟對話框。

### 三種 pattern_type

| 類型 | 比對方式 | 適合場景 |
|---|---|---|
| `keyword` | `pattern.lower() in merchant.lower()` | 關鍵字泛匹配（「星巴克」） |
| `exact` | `pattern == merchant`（大小寫敏感）| 精確商家名（「Starbucks #1234」） |
| `regex` | `re.search(pattern, merchant)`（fail-soft、100ms timeout）| 變化規則（如 `^蝦皮商城.*` ）|

### 優先序與 priority 欄位

- 同樣命中時，`priority` 數值大者勝出（DESC + id ASC）
- 規則命中後跳過內建 engine
- 任何規則 fail-soft：regex compile 失敗、執行 > 100ms 都會 log warning，但**不阻斷其他規則**

### Best practice

1. **先用 keyword**：最簡單、無 ReDoS 風險
2. **regex 慎用 nested quantifier**：`(a+)+` 之類 pattern 會在惡意輸入下卡住，靠 100ms timeout 保護；UI 對話框會即時顯示警示 banner
3. **priority 留空隙**：建議 10 / 20 / 30，方便插隊，避免後續整批調整
4. **disabled 取代刪除**：暫停某規則時用 `enabled=false` 保留歷史，便於追溯分類差異
5. **建立前先測**：對話框內含「測試規則」區塊，輸入 sample merchant 字串後即時呼叫 `/api/rules/test`（與 pipeline 走同一 matcher），確認命中再建立

### API 範例

```bash
# 列出全部規則（priority DESC + id ASC）
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/rules?enabled=true"

# 新增 keyword 規則：星巴克 → 餐飲
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pattern":"星巴克","pattern_type":"keyword","category_id":1,"priority":10,"enabled":true}' \
  "$BASE/api/rules"

# 測試規則（不寫 DB，回傳是否命中）
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pattern":"^蝦皮","pattern_type":"regex","sample_text":"蝦皮商城#001"}' \
  "$BASE/api/rules/test"

# 刪除
curl -fsS -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/rules/12"
```

> `category_id` 必須對應 `categories` 表既有 id；錯誤回 422。

---

## 3. 付款提醒設定

進入 `/settings/reminders` 即可。

### 行為

- 列出全部「未付」帳單，每筆獨立設定
- 預設 `enabled=true / days_before=[3, 1] / channel=telegram`
- `days_before`：在帳單到期前 N 天推送（多值以逗號分隔輸入，blur 解析）
- `channel`：`telegram` / `ui_banner` / `both`

### 「測試發送」按鈕

| channel | 行為 |
|---|---|
| `telegram` / `both` | 立即送一則 Telegram 訊息，UI 顯示 ✓ |
| `ui_banner` | 不外送，UI 顯示「以 banner 提示」 |

> Telegram 未設定時 `telegram` channel fail-soft，scheduler 不會 raise；但 settings 頁的「測試」按鈕會回明確錯誤。

---

## 4. 預算與告警

進入 `/settings/budgets`。

### 三種 scope

| scope | scope_ref | 用途 |
|---|---|---|
| `monthly_total` | 必為空 | 每月總支出上限 |
| `monthly_category` | `categories.category` 字串 | 單類別上限（例：「餐飲」） |
| `monthly_bank` | `bank_configs.bank_code` | 單銀行上限（例：「CTBC」） |

`amount_minor_units` 以「分」為單位儲存（10000 = NT$100）；UI 自動換算。

### Threshold ladder

每筆預算可設 `alert_threshold_percent`（預設 80）。Scheduler 每日 02:00 跑 `evaluate_budgets()`：

1. 累計當月該 scope 已花金額
2. 若達 `alert_threshold_percent` 且該門檻當月未觸發 → 寫 `BudgetAlert` + 推 Telegram
3. 若達 100%（且尚未觸發）→ 同樣處理

`(budget_id, period_year_month, threshold_breached_percent)` 為去重 key，**同月同階不重複推**。

### Banner

`/overview` 頂部 `<BudgetAlertBanner>` 拉 `/api/budgets/alerts/active`。點「確認」呼叫 `POST /api/budgets/alerts/{id}/acknowledge`，banner 立即消失。

### 範例：建立每月餐飲 5,000 元預算（80% 告警）

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "monthly_category",
    "scope_ref": "餐飲",
    "amount_minor_units": 500000,
    "alert_threshold_percent": 80,
    "enabled": true
  }' "$BASE/api/budgets"
```

---

## 5. Insights 頁

`/insights` 取代舊 `/analytics`（保留 redirect）。

| 區塊 | 來源 | 切換 |
|---|---|---|
| 月趨勢 | `/api/analytics/trend?months=6\|12\|24` | trend_months select |
| 銀行對比（長條圖）| `/api/analytics/compare/banks?year=&month=` | 共用頁面頂部 FilterBar |
| 年度對比（折線圖）| `/api/analytics/compare/years?metric=total\|count` | metric select |
| 商家排行（表格）| `/api/analytics/top-merchants?limit=5\|10\|20&period=all\|month\|year` | period / limit select |
| 類別 vs 上月（list） | `/api/analytics/categories?month=&compare_with_previous=true` | 需先填 month；上月為 0 顯示「—」 |

> 所有 query 都共用 dashboard 既有 `Authorization: Bearer` token。

---

## 6. 匯出（CSV / Excel）

`/insights` 右上角「匯出」按鈕開啟 `<ExportDialog>`，可選：

- `format`：`csv` / `xlsx`
- `start` / `end`：日期範圍
- `bank`：bank_code
- `category`：類別字串
- `include_user_fields`：勾選後加 `manual_category_override / tags / merchant_alias / note` 四欄

CSV 走 `session.stream()` + `csv.writer` 逐筆 yield；xlsx 走 `openpyxl.Workbook(write_only=True)` + tempfile 串流回傳，避免大量資料 OOM。

```bash
# 從 CLI 直接 curl
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/transactions/export?format=csv&start=2026-01-01&end=2026-12-31&include_user_fields=true" \
  -o ccas-2026.csv
```

---

## 7. 升級相容性

從更舊版本升級：

1. `docker compose pull && up -d` 自動跑 alembic upgrade head
2. 既有 transactions 的 `manual_category_override` 欄位預設 `false`、`tags=[]`、`merchant_alias=''`、`note=null`
3. 既有 `analytics_v1` API 全部保留（`/api/analytics/categories` 不帶 `compare_with_previous` 仍走 legacy schema）
4. PaymentReminder 表保留為 sent log；新表 `reminder_settings` 獨立

詳細 migration 影響見 [docs/upgrade-guide.md](upgrade-guide.md)。
