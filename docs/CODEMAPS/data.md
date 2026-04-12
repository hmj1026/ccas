<!-- Generated: 2026-04-12 | Files scanned: 5 | Token estimate: ~680 -->

# Data

## Database

SQLite + aiosqlite, WAL mode, async sessions (`expire_on_commit=False`)

ORM: SQLAlchemy 2.0 (`Mapped[T]` style) in `backend/src/ccas/storage/models.py`

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
| category | str? | filled by classifier |
| note | str? | |
| created_at | datetime | |

### categories
keyword (str, UQ) -> category (str), source (str, `"seed"` / `"user"`)

### bank_configs
bank_code (str, UQ), bank_name, gmail_filter, pdf_password_rule?, active_parser_version, is_active

### staged_attachments
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| bank_code | str | |
| source_type | str | `gmail` / `web`（新增） |
| gmail_message_id | str | |
| gmail_attachment_id | str | legacy, 舊資料保留 |
| gmail_part_id | str? | 新 dedupe key（Gmail MIME part），舊列 NULL 時 fallback 檔名 |
| message_date | datetime | |
| original_filename | str | |
| staged_path | str? | |
| status | str | staged/decrypted/parsed/skipped/*_failed |
| error_reason | str? | |
| **UQ** | (gmail_message_id, gmail_part_id) | 舊 UQ `(message_id, attachment_id)` 已替換 |

### payment_reminders
bill_id (FK), reminder_type, sent_at | **UQ** (bill_id, reminder_type)

## Relationships

```
Bill 1--* Transaction  (cascade delete)
Bill 1--* PaymentReminder
```

## Migrations

| Rev | Description |
|-----|-------------|
| 2b407df3b1b5 | Initial tables (bills, transactions, categories, bank_configs) |
| 08828cd4e8ca | Add staged_attachments |
| c3a1f5e8d9b2 | Add payment_reminders |
| ca5a1f05744d | Add bill.is_notified column |
| 11ca9b74b00c | Add staged_attachment.source_type (`gmail` / `web`) |
| 1334f4fe5f73 | Add staged_attachment.gmail_part_id + switch UQ to `(message_id, part_id)` |
| 066eb5d1c70c | Add categories.source (`"seed"` / `"user"`) |
