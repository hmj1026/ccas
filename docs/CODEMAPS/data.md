<!-- Generated: 2026-05-10 | Files scanned: 12 | Token estimate: ~1020 -->

# Data

## Database

SQLite + aiosqlite, WAL mode + `PRAGMA busy_timeout=30000`（per-connection on `connect`，避開 scheduler heartbeat / worker / backend GET 的 WAL 寫入競爭），async sessions (`expire_on_commit=False`)

ORM: SQLAlchemy 2.0 (`Mapped[T]` style) in `backend/src/ccas/storage/models.py`
SQLite triggers 同步維護 `updated_at`（避開 ORM `onupdate=` 在 Core-style bulk UPDATE 不觸發的問題）。

## Tables

### bills
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | autoincrement |
| bank_code | str | |
| billing_month | str | |
| total_amount | int | TWD（整數元） |
| due_date | date | |
| is_paid | bool | |
| is_notified | bool | default False, set after Telegram notify |
| file_path | str? | |
| created_at | datetime | |
| **UQ** | (bank_code, billing_month) | |

### transactions
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| bill_id | int FK(bills) | cascade delete |
| trans_date | date | |
| posting_date | date? | |
| merchant | str | |
| amount | int | TWD（整數元） |
| currency | str | default "TWD" |
| original_amount | int? | foreign currency |
| card_last4 | str? | |
| installment_current/total | int? | |
| category | str? | filled by classifier or manual override |
| note | str? | |
| manual_category_override | bool | default 0；true 時 classifier 不再覆寫 category |
| tags | JSON | default `[]` |
| merchant_alias | str | default ""；使用者自訂顯示名 |
| created_at | datetime | |
| updated_at | datetime | trigger 維護 |
| **IX** | (category, trans_date) | analytics filter 加速 |

### categories
keyword (str, UQ) -> category (str), source (str, `"seed"` / `"user"`)

### bank_configs
bank_code (str, UQ), bank_name, gmail_filter, pdf_password_rule?, active_parser_version, is_active

### staged_attachments
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| bank_code | str | |
| source_type | str | `gmail` / `web` |
| gmail_message_id | str | |
| gmail_attachment_id | str | legacy, 舊資料保留 |
| gmail_part_id | str? | dedupe key（Gmail MIME part），舊列 NULL 時 fallback 檔名 |
| message_date | datetime | |
| original_filename | str | |
| staged_path | str? | 相對 STAGING_DIR 路徑 |
| status | str | staged/decrypted/parsed/skipped/*_failed |
| error_reason | str? | |
| **UQ** | (gmail_message_id, gmail_part_id) | |

### payment_reminders
bill_id (FK), reminder_type, sent_at | **UQ** (bill_id, reminder_type)

### reminder_settings  *(每張 bill 可選擇覆寫預設提醒策略)*
| Column | Type | Notes |
|--------|------|-------|
| bill_id | int PK FK(bills) | |
| enabled | bool | default 1 |
| days_before | JSON | default `[3, 1]`；提醒提前天數 |
| channel | str | default `telegram` |
| created_at / updated_at | datetime | trigger 維護 |

### classification_rules  *(使用者自訂分類規則，優先於 keyword categories)*
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| pattern | str | |
| pattern_type | str | `contains` / `regex` / `prefix` 等 |
| category_id | int FK(categories.id) | |
| priority | int | default 0；DESC 排序 |
| enabled | bool | default 1 |
| created_at / updated_at | datetime | trigger 維護 |
| **IX** | (priority DESC, enabled) | classifier 熱路徑 |

### budgets
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| scope | str | `total` / `bank` / `category` |
| scope_ref | str? | bank_code 或 category 名；scope=`total` 時 NULL |
| amount_minor_units | int | TWD（整數元） |
| alert_threshold_percent | int | default 80 |
| enabled | bool | default 1 |
| created_at / updated_at | datetime | trigger 維護 |
| **IX** | (scope, scope_ref) | |

### budget_alerts
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| budget_id | int FK(budgets) | |
| period_year_month | str(7) | `YYYY-MM` |
| threshold_breached_percent | int | |
| current_amount_minor_units | int | |
| triggered_at | datetime | |
| acknowledged_at | datetime? | UI ack 後寫入 |

### pipeline_runs  *(pipeline-operations-center)*
| Column | Type | Notes |
|--------|------|-------|
| id | str(36) PK | UUID |
| job_id | str(64) | RQ job id |
| status | str(16) | `queued` / `running` / `succeeded` / `failed` / `cancelled` |
| triggered_by | str(32) | UI 使用者 / scheduler / cli |
| params | JSON | PipelineOptions 序列化 |
| current_stage | str(16)? | ingest / decrypt / parse / classify / notify |
| current_stage_processed | int | default 0 |
| current_stage_total | int | default 0 |
| stage_summary | JSON | 各 stage `{processed, total, errors}` |
| error_message | text? | |
| started_at / completed_at | datetime? | |
| created_at / updated_at | datetime | trigger 維護 |
| **IX** | created_at DESC、status | |

> `DbProgressReporter.stage_finished` 對 `database is locked` 自動重試 3 次（0.1 / 0.5 / 2 秒 backoff），保護 `stage_summary` RMW 不被 WAL 寫入競爭中斷（PR #6 / #11）。

### bank_settings  *(setup wizard — 取代 bank_configs.is_active 的細項)*
code(PK), enabled, display_name?, notes?, created_at, updated_at（trigger 維護）

### bank_secrets  *(setup wizard — 加密的 PDF 密碼)*
bank_code(PK), encrypted_password, created_at, updated_at（trigger 維護）

### gmail_oauth_state  *(setup wizard — OAuth PKCE state)*
state(PK), code_verifier, created_at

## Relationships

```
Bill 1--* Transaction      (cascade delete)
Bill 1--* PaymentReminder
Bill 1--1 ReminderSetting  (per-bill override)
Budget 1--* BudgetAlert
Category 1--* ClassificationRule
PipelineRun (no FK，獨立紀錄)
```

## Migrations (依 down_revision 鏈序)

| Rev | Description |
|-----|-------------|
| 2b407df3b1b5 | Initial tables (bills, transactions, categories, bank_configs) |
| 08828cd4e8ca | Add staged_attachments |
| c3a1f5e8d9b2 | Add payment_reminders |
| ca5a1f05744d | Add bill.is_notified column |
| 11ca9b74b00c | Add staged_attachment.source_type (`gmail` / `web`) |
| 1334f4fe5f73 | Add staged_attachment.gmail_part_id + switch UQ to `(message_id, part_id)` |
| 066eb5d1c70c | Add categories.source (`"seed"` / `"user"`) |
| 2570bbdebf54 | Add setup tables (bank_settings、bank_secrets、gmail_oauth_state) + updated_at triggers |
| 0a2c400f1179 | Add pipeline_runs（含 stage_summary、created_at DESC index、updated_at trigger） |
| a4b8c2d6e0f1 | Add transactions user fields (manual_category_override、tags、merchant_alias、updated_at) + (category, trans_date) index |
| 5f9d4a7b3c8e | Add classification_rules、budgets、budget_alerts（含 priority DESC index） |
| 9b3e2c8a4f10 | Add reminder_settings（per-bill override，含 updated_at trigger） |
