## MODIFIED Requirements

### Requirement: Bill 新增通知追蹤欄位

`Bill` model SHALL 新增 `is_notified` 欄位追蹤通知狀態。

#### Scenario: 新帳單預設未通知
- **WHEN** 建立新的 Bill 記錄
- **THEN** `is_notified` SHALL 預設為 `False`

#### Scenario: 既有帳單視為已通知
- **WHEN** Alembic migration 套用至既有資料庫
- **THEN** 所有現有 Bill 的 `is_notified` SHALL 設為 `True`（避免舊帳單重發通知）
