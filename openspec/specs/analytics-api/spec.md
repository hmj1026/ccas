# analytics-api Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
### Requirement: 提供月趨勢 API
系統 SHALL 提供 `GET /api/analytics/trend`，回傳最近 N 個月份的消費總額序列；若未提供 `months`，預設為 6。

#### Scenario: 回傳最近 6 個月趨勢
- **WHEN** 前端呼叫 `GET /api/analytics/trend`
- **THEN** API 會回傳最近 6 個月份與各月份總消費

### Requirement: 提供類別分布 API
系統 SHALL 提供 `GET /api/analytics/categories`，回傳指定月份各分類的消費總額；若未提供 `month`，預設為當月。

#### Scenario: 回傳指定月份類別分布
- **WHEN** 前端呼叫 `GET /api/analytics/categories?month=2026-03`
- **THEN** API 會回傳 `2026-03` 各分類的彙總金額

### Requirement: 提供銀行比較 API
系統 SHALL 提供 `GET /api/analytics/banks`，回傳指定月份按銀行彙總的消費總額；若未提供 `month`，預設為當月。

#### Scenario: 回傳指定月份銀行比較資料
- **WHEN** 前端呼叫 `GET /api/analytics/banks?month=2026-03`
- **THEN** API 會回傳 `2026-03` 各銀行的彙總金額

