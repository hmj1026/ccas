## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: 既有 GET /api/analytics/categories 加 compare_with_previous

**Reason**: union response（同一端點依 `compare_with_previous` 切換兩種 schema）對前端 codegen 不友善，且違反 `python-api.md`「每端點固定 `response_model=ApiResponse[T]`」慣例。
**Migration**: 月對月比較改用 `GET /api/analytics/categories/compare?month=YYYY-MM`；基礎分布沿用 `GET /api/analytics/categories`（不再接受 `compare_with_previous` 參數）。

## ADDED Requirements

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
