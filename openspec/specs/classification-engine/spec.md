# classification-engine Specification

## Purpose
TBD - created by archiving change keyword-classifier. Update Purpose after archive.
## Requirements
### Requirement: 以 deterministic 規則匹配商家分類
系統 SHALL 根據正規化後的商家名稱與 `categories.keyword` 做匹配，並在多個規則同時命中時採用最長關鍵字優先、同長度取較小 `id` 的規則。

#### Scenario: 最長關鍵字優先
- **WHEN** 同一筆商家名稱同時命中多個關鍵字，且其中一個關鍵字字串更長
- **THEN** 系統會採用較長關鍵字對應的分類結果

#### Scenario: 同長度關鍵字以較小 id 決定
- **WHEN** 同一筆商家名稱同時命中兩個以上長度相同的關鍵字
- **THEN** 系統會採用 `categories.id` 較小的那筆規則

### Requirement: 無命中時回傳 `未分類`
系統 SHALL 在沒有任何關鍵字規則命中時，回傳固定分類值 `未分類`。

#### Scenario: 商家名稱沒有任何匹配規則
- **WHEN** 某筆交易的商家名稱與現有關鍵字都不匹配
- **THEN** 分類引擎回傳 `未分類`

