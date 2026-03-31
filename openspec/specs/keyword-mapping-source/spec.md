# keyword-mapping-source Specification

## Purpose
TBD - created by archiving change keyword-classifier. Update Purpose after archive.
## Requirements
### Requirement: 從 `categories` 資料表載入分類規則
系統 SHALL 從 `categories` 資料表讀取所有關鍵字與對應分類，作為 keyword classifier 的規則來源。

#### Scenario: 載入所有分類映射
- **WHEN** 分類引擎初始化或重新載入規則
- **THEN** 系統會讀取 `categories` 資料表中的所有 `keyword` 與 `category` 組合

#### Scenario: 規則異動影響後續分類
- **WHEN** `categories` 資料表中的關鍵字映射被新增、修改或刪除
- **THEN** 後續分類執行會以更新後的資料表內容為準

