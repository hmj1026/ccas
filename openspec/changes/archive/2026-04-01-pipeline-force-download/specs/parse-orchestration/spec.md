## ADDED Requirements

### Requirement: Force 模式繞過 parse 去重
當 `PipelineOptions.force = True` 時，系統 SHALL 在發現已存在的 `Bill`（以 `bank_code + billing_month` 識別）後，刪除該舊 `Bill` 及其關聯的 `Transaction` 記錄，再重新執行 parser 建立新的 Bill 與 Transaction。

#### Scenario: Force 模式重新解析已存在的帳單
- **WHEN** `force = True` 且某附件解析結果的 `(bank_code, billing_month)` 已存在於 `Bill` 表
- **THEN** 系統刪除舊的 `Bill`（cascade 刪除其 `Transaction`），再建立新的 `Bill` 和 `Transaction` 記錄

#### Scenario: 非 Force 模式維持去重行為
- **WHEN** `force = False`（預設）且某帳單已存在於 `Bill` 表
- **THEN** 系統跳過該帳單的 parse，行為與變更前完全一致

#### Scenario: Force 模式下通知以新 Bill ID 觸發
- **WHEN** `force = True` 且舊 Bill 被刪除重建
- **THEN** 新 Bill 獲得新的 ID，notification 階段以新 ID 判斷是否已通知（自然去重）
