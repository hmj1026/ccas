## MODIFIED Requirements

### Requirement: 帳單主表資料模型

#### MODIFIED Scenario: 建立帳單紀錄
- **WHEN** 建立一筆 `Bill`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime（`datetime.now(UTC)`），而非 naive datetime

### Requirement: 消費明細資料表模型

#### MODIFIED Scenario: 消費明細可連結到帳單
- **WHEN** 建立一筆具有有效 `bill_id` 的 `Transaction`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime

### Requirement: Staging 附件資料表模型

#### MODIFIED Scenario: 建立 staging 紀錄
- **WHEN** 建立一筆 `StagedAttachment`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime

### Requirement: 付款提醒資料表模型

#### MODIFIED Scenario: 建立提醒紀錄
- **WHEN** 建立一筆 `PaymentReminder`
- **THEN** `sent_at` 會自動設定為 timezone-aware UTC datetime
