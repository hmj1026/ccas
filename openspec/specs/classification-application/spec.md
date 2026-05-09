# classification-application Specification

## Purpose
TBD - created by archiving change keyword-classifier. Update Purpose after archive.
## Requirements
### Requirement: 將分類結果寫入交易資料
系統 SHALL 能將分類引擎的結果寫入 `Transaction.category`，用於新解析交易與既有交易的重跑分類。

#### Scenario: 新交易建立時套用分類
- **WHEN** 系統為某筆新解析交易執行分類
- **THEN** `Transaction.category` 會被填入匹配結果或 `未分類`

#### Scenario: 對既有交易重跑分類
- **WHEN** 系統對既有交易執行 reclassification
- **THEN** `Transaction.category` 會根據最新規則被重新計算與更新

### Requirement: 分類結果不修改原始交易欄位
系統 SHALL 只更新分類欄位，而不改寫原始交易資料，例如商家名稱、日期或金額。

#### Scenario: 重跑分類保留原始交易資訊
- **WHEN** 某批交易重新套用分類規則
- **THEN** 除了 `Transaction.category` 外，其他原始交易欄位內容都保持不變

