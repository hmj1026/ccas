## MODIFIED Requirements

### Requirement: 帳單主表資料模型

系統 SHALL 維持 `Bill` 資料模型的既有欄位與唯一約束，且 `created_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### MODIFIED Scenario: 建立帳單紀錄
- **WHEN** 建立一筆 `Bill`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime（`datetime.now(UTC)`），而非 naive datetime

### Requirement: 消費明細資料表模型

系統 SHALL 維持 `Transaction` 資料模型的既有欄位與外鍵關聯，且 `created_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### MODIFIED Scenario: 消費明細可連結到帳單
- **WHEN** 建立一筆具有有效 `bill_id` 的 `Transaction`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime
