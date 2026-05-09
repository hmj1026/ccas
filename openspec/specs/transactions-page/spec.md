# transactions-page Specification

## Purpose
TBD - created by archiving change frontend-dashboard. Update Purpose after archive.
## Requirements
### Requirement: 提供交易搜尋與篩選頁面
系統 SHALL 提供 Transactions 頁面，支援依月份、銀行、分類與關鍵字搜尋交易，並顯示分頁表格。

#### Scenario: 套用篩選條件後更新表格
- **WHEN** 使用者在 `/transactions` 頁面調整月份、銀行、分類或搜尋字串
- **THEN** 表格會以對應條件重新查詢並顯示結果

#### Scenario: 篩選條件同步到 URL
- **WHEN** 使用者在 `/transactions` 頁面套用篩選
- **THEN** 主要篩選條件會同步到 URL query params

### Requirement: 提供 CSV 匯出操作
系統 SHALL 在 Transactions 頁面提供 CSV 匯出按鈕，並使用目前的篩選條件匯出資料。

#### Scenario: 使用目前篩選條件匯出 CSV
- **WHEN** 使用者在套用篩選後點擊 CSV 匯出
- **THEN** 系統會匯出符合目前篩選條件的交易資料

