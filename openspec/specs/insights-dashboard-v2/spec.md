# insights-dashboard-v2 Specification

## Purpose
TBD - created by archiving change bills-management-and-insights. Update Purpose after archive.
## Requirements
### Requirement: GET /api/analytics/compare/banks 銀行對比

系統 SHALL 提供 `GET /api/analytics/compare/banks?year=&month=` 端點，回傳指定年月各銀行的金額與筆數（GROUP BY bank_code）。Response SHALL 為陣列：`[{bank_code, bank_name, total}, ...]`（`total` 為 NTD 整數元，不乘 100），按 total DESC 排序。

#### Scenario: 月度銀行對比

- **WHEN** `GET /api/analytics/compare/banks?year=2026&month=4`
- **THEN** response SHALL 含 2026-04 各銀行的累計金額與筆數、按金額排序

#### Scenario: 跨月對比（year only）

- **WHEN** `GET /api/analytics/compare/banks?year=2026`（不帶 month）
- **THEN** SHALL 回該年累計、含 month-by-month breakdown 子欄位 `monthly: [{month: int, amount: int}]`

#### Scenario: 空資料正確處理

- **WHEN** 指定 year/month 完全無 transactions
- **THEN** SHALL 回空陣列 `[]`、HTTP 200，前端可顯示「該月份無資料」

### Requirement: GET /api/analytics/compare/years 年度對比

系統 SHALL 提供 `GET /api/analytics/compare/years?metric=total|count` 端點，回傳近 5 年各年的金額或筆數（依 metric）。Response 為 `{years: [int], values: [int]}` 或更結構化的陣列。

#### Scenario: 預設 metric=total

- **WHEN** `GET /api/analytics/compare/years` 不帶 metric
- **THEN** SHALL 回近 5 年總金額；若資料不足 5 年（如僅 2 年）則 SHALL 僅回實際有資料的年份

#### Scenario: metric=count 改回筆數

- **WHEN** `GET /api/analytics/compare/years?metric=count`
- **THEN** values SHALL 為各年交易筆數

### Requirement: GET /api/analytics/top-merchants 商家排行

系統 SHALL 提供 `GET /api/analytics/top-merchants?limit=&period=year|month&offset_months=` 端點，回傳指定 period 內金額最高的商家排行（GROUP BY description）。預設 limit=10、period=month、offset_months=0（當月）。Response 為 `[{merchant, total, count}, ...]`（`total` 為 NTD 整數元，不乘 100）。

#### Scenario: 預設取當月 top 10

- **WHEN** `GET /api/analytics/top-merchants`
- **THEN** SHALL 回當月金額前 10 商家

#### Scenario: offset_months 取過去月份

- **WHEN** `GET /api/analytics/top-merchants?offset_months=1`
- **THEN** SHALL 回上個月 top 10

#### Scenario: period=year 取年度排行

- **WHEN** `GET /api/analytics/top-merchants?period=year`
- **THEN** SHALL 回當年累計 top N 商家

#### Scenario: limit 上限 50

- **WHEN** `?limit=200`
- **THEN** 系統 SHALL 自動 cap 為 50、不報錯（避免大量 result）

### Requirement: GET /api/analytics/categories 與 /categories/compare 拆分端點

`GET /api/analytics/categories` SHALL 固定回傳 `ApiResponse[list[CategoryItem]]`（`{category, total}`，`total` 為 NTD 整數元），不接受 `compare_with_previous` 參數。系統 SHALL 另提供 `GET /api/analytics/categories/compare` 端點：`month`（YYYY-MM）為必填，回傳 `ApiResponse[list[CategoryWithCompareItem]]`（`{category, total, previous_total, change_percent}`），`change_percent = (total - previous_total) / previous_total * 100`。

#### Scenario: 基礎端點回應形狀固定

- **WHEN** `GET /api/analytics/categories?month=2026-05`
- **THEN** response 每項 SHALL 僅含 `{category, total}`，形狀不隨參數改變

#### Scenario: compare 端點月對月比較

- **WHEN** `GET /api/analytics/categories/compare?month=2026-05`
- **THEN** response 每項 SHALL 含 `{category, total, previous_total, change_percent}`；前月無資料或為 0 時 `change_percent` SHALL 為 null（避免除 0）

#### Scenario: compare 端點 month 必填

- **WHEN** `GET /api/analytics/categories/compare`（缺 month）
- **THEN** SHALL 回 422

### Requirement: /insights 前端頁面整合

系統 SHALL 提供 `frontend/src/pages/insights.tsx`，路由 `/insights`。頁面 SHALL 包含五個區塊：(1) 月趨勢圖（既有）+ 月對月變化百分比、(2) 類別分布餅圖（既有）+ 與上月對比、(3) 銀行對比堆疊長條圖（新）、(4) 年度對比折線圖（新）、(5) 商家排行表格（新）。所有圖表 SHALL 響應式、行動裝置可用。

#### Scenario: 既有 /analytics 路由 redirect

- **WHEN** 使用者開 `/analytics`（舊書籤）
- **THEN** frontend SHALL redirect 至 `/insights`、不破壞既有書籤

#### Scenario: NAV 標籤更新

- **WHEN** 使用者瀏覽主 NAV
- **THEN** 標籤 SHALL 顯示「Insights」（中文 UI 顯示為「洞察」）、icon 換為 `BarChart3` 或 `Sparkles`

#### Scenario: 區塊載入策略

- **WHEN** 頁面初次載入
- **THEN** 五個區塊 SHALL 各自獨立 query（React Query），任一 query 失敗 SHALL 不阻斷其他區塊渲染、失敗區塊顯示 inline error 與 retry 按鈕

#### Scenario: 月對月百分比顯示

- **WHEN** 月趨勢區塊渲染當前月份
- **THEN** 數字旁 SHALL 顯示 `+12.3%`（綠）或 `-5.1%`（紅）對比上月

### Requirement: GET /api/transactions/export CSV/Excel 匯出

系統 SHALL 提供 `GET /api/transactions/export?format=csv|xlsx&start=&end=&bank=&category=&include_user_fields=` 端點，streaming 匯出 transactions。CSV 用 `csv.writer` + StreamingResponse；Excel 用 `openpyxl.Workbook(write_only=True)`。Filter 支援日期範圍（start / end ISO date）、銀行 code、category id；`include_user_fields=true` 時欄位含 note / tags / merchant_alias / manual_category_override。

#### Scenario: CSV streaming export

- **WHEN** `GET /api/transactions/export?format=csv&start=2026-01-01&end=2026-12-31`
- **THEN** response Content-Type SHALL 為 `text/csv; charset=utf-8`、`Content-Disposition: attachment; filename="ccas-transactions-2026-01-01-to-2026-12-31.csv"`、body SHALL chunked、不於 memory 累積完整檔案

#### Scenario: Excel 匯出

- **WHEN** `?format=xlsx`
- **THEN** response Content-Type SHALL 為 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`、用 openpyxl write_only mode 產生、單 sheet 名稱「Transactions」

#### Scenario: include_user_fields=true 含個人欄位

- **WHEN** `?include_user_fields=true`
- **THEN** 匯出欄位 SHALL 含 `note, tags, merchant_alias, manual_category_override` 4 欄；預設（false）僅含原始 transaction 欄位

#### Scenario: 大量資料 streaming 不 OOM

- **WHEN** 匯出 50K 筆 transactions
- **THEN** backend peak memory SHALL < 100MB、response 持續流出 row 不卡頓

#### Scenario: 篩選空結果回空檔案

- **WHEN** filter 條件無匹配交易
- **THEN** SHALL 回 200 + 僅含 header row 的 CSV 或僅含 header 的 xlsx，不 raise 404

#### Scenario: 422 invalid format

- **WHEN** `?format=pdf`
- **THEN** SHALL 回 422、錯誤訊息「format 必須為 csv 或 xlsx」

### Requirement: ExportDialog 前端組件

系統 SHALL 提供 `frontend/src/components/export-dialog.tsx`：對話框含日期範圍 picker、銀行 multi-select、類別 multi-select、format radio (CSV / Excel)、include_user_fields toggle、「匯出」按鈕。按下後構造 query string 觸發瀏覽器下載（`<a href={url} download>` 或 `window.open`）。

#### Scenario: 預設日期範圍為當年

- **WHEN** 對話框開啟
- **THEN** 日期範圍 SHALL 預設 `2026-01-01` 至今日（依當前年）

#### Scenario: 銀行 / 類別 multi-select 可空（全選）

- **WHEN** 不選任何銀行 / 類別
- **THEN** query string SHALL 不附 `bank` 或 `category` 參數、後端視為「全部」

#### Scenario: 匯出進度提示

- **WHEN** 使用者點「匯出」
- **THEN** 對話框 SHALL 顯示「匯出中，請稍候，瀏覽器會自動下載」+ spinner；下載開始後關閉對話框並 toast「匯出完成」

### Requirement: insights 查詢效能與索引

`/insights` 各端點查詢 SHALL 使用 SQL aggregate（GROUP BY）而非 Python 端累加。對 transactions 表 SHALL 補強複合索引 `(category_id, transaction_date)` 與 `(bank_code, transaction_date)`，配合既有 `(transaction_date)` 索引覆蓋常見 insights 查詢。

#### Scenario: 銀行對比 query 命中索引

- **WHEN** `/api/analytics/compare/banks?year=2026&month=4`
- **THEN** SQLite EXPLAIN QUERY PLAN SHALL 顯示使用 `(bank_code, transaction_date)` 索引

#### Scenario: 50K 筆資料下查詢 < 500ms

- **WHEN** transactions 表有 50K 筆、執行銀行對比 query
- **THEN** 後端 response time SHALL < 500ms（不含網路）

#### Scenario: 對比 query 限定 24 個月

- **WHEN** `/api/analytics/compare/years` 跨多年但僅有 5 年資料
- **THEN** 後端 SHALL 對年度對比限制最近 60 個月（5 年）資料、避免無限 scan
