## ADDED Requirements

### Requirement: 只處理尚未完成解析的 staged attachment
系統 SHALL 只對尚未標記為成功解析的 staged attachment 執行 parser orchestration，避免重複處理已完成項目。

#### Scenario: 已成功解析的附件會被略過
- **WHEN** 某個 staged attachment 已被標記為 `parsed`
- **THEN** parser orchestration 不會再次對其建立重複的 `Bill` 與 `Transaction`

### Requirement: 解析成功後寫入帳單與交易資料
系統 SHALL 在 staged attachment 成功解析後，建立對應的 `Bill` 與多筆 `Transaction`，並將該附件狀態更新為 `parsed`。

#### Scenario: 成功解析後寫入資料庫
- **WHEN** 某個 staged attachment 透過某個 bank parser 成功產出 `ParseResult`
- **THEN** 系統會持久化一筆 `Bill`、多筆 `Transaction`，並將該附件標記為 `parsed`

#### Scenario: 分類尚未執行時保留原始交易資料
- **WHEN** parser orchestration 建立 `Transaction` 紀錄
- **THEN** 系統會先保存原始交易欄位，而分類欄位可待後續 classifier 流程補齊

### Requirement: 所有 parser 失敗時標記為 `parse_failed`
系統 SHALL 在所有候選 parser 都無法成功解析某個附件時，將該附件標記為 `parse_failed`，並保存錯誤原因。

#### Scenario: 全部 parser 版本都無法解析
- **WHEN** 某個 staged attachment 經過所有候選 parser 後仍無法成功解析
- **THEN** 系統會將該附件標記為 `parse_failed`，並記錄可供人工審查的失敗原因

#### Scenario: `parse_failed` 附件可被視為人工審查待辦
- **WHEN** 某個 staged attachment 的狀態為 `parse_failed`
- **THEN** 後續流程可將其視為人工審查佇列中的待處理項目
