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

### Requirement: 所有分類路徑產生相同的分類判定
系統 SHALL 以同一個分類判定決定交易的消費類別，不論呼叫端是 pipeline classify 階段、全量重新分類，還是清除手動分類覆寫的端點。判定順序依 `classification-rules-management` 的「classify 階段優先序」，手動分類覆寫依 `transaction-editing` 的「classify 階段尊重 manual_category_override」。分類判定 SHALL 回報是哪一步決定的（`manual_override`、`user_rule`、`keyword`、`default`），並 SHALL 以交易的原始商家名稱比對，SHALL NOT 使用商家別名。

#### Scenario: 清除覆寫後的結果等於 pipeline 結果
- **WHEN** 某筆交易的手動分類覆寫被清除，且同一組分類規則與關鍵字規則下 pipeline classify 階段處理同一筆交易
- **THEN** 兩者 SHALL 得到相同的消費類別與相同的判定來源

#### Scenario: 手動分類覆寫在每個路徑都保留既有消費類別
- **WHEN** 交易的 `manual_category_override = true`，且由 pipeline classify 階段或全量重新分類處理
- **THEN** 分類判定 SHALL 回報來源 `manual_override`，且兩個路徑都 SHALL NOT 改寫該交易的消費類別

#### Scenario: 商家別名不影響分類
- **WHEN** 交易的商家別名命中某條分類規則，但原始商家名稱不命中
- **THEN** 分類判定 SHALL NOT 採用該規則
