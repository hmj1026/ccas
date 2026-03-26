## ADDED Requirements

### Requirement: Bills table model
The system SHALL define a SQLAlchemy ORM model `Bill` with fields: `id` (INTEGER, PK, autoincrement), `bank_code` (TEXT, not null), `billing_month` (TEXT, not null, format YYYY-MM), `total_amount` (INTEGER, not null), `due_date` (DATE, not null), `is_paid` (BOOLEAN, default false), `file_path` (TEXT), `created_at` (DATETIME, default utcnow). A unique constraint SHALL exist on (`bank_code`, `billing_month`).

#### Scenario: Bill record creation
- **WHEN** a new Bill is created with bank_code="CTBC", billing_month="2026-03", total_amount=15000, due_date="2026-04-15"
- **THEN** the record is persisted with is_paid=false and created_at set automatically

#### Scenario: Duplicate bill prevention
- **WHEN** a Bill with bank_code="CTBC" and billing_month="2026-03" already exists and another with the same values is inserted
- **THEN** the database raises an IntegrityError

### Requirement: Transactions table model
The system SHALL define a SQLAlchemy ORM model `Transaction` with fields: `id` (INTEGER, PK, autoincrement), `bill_id` (INTEGER, FK to bills.id, not null), `trans_date` (DATE, not null), `merchant` (TEXT, not null), `amount` (INTEGER, not null), `currency` (TEXT, default "TWD"), `original_amount` (INTEGER, nullable), `card_last4` (TEXT, nullable), `installment_current` (INTEGER, nullable), `installment_total` (INTEGER, nullable), `category` (TEXT, nullable), `note` (TEXT, nullable), `created_at` (DATETIME, default utcnow).

#### Scenario: Transaction linked to bill
- **WHEN** a Transaction is created with a valid bill_id
- **THEN** the record is persisted and accessible via `bill.transactions` relationship

#### Scenario: Foreign key enforcement
- **WHEN** a Transaction is created with a bill_id that does not exist in bills
- **THEN** the database raises an IntegrityError

#### Scenario: Installment fields nullable
- **WHEN** a non-installment Transaction is created with installment_current=None and installment_total=None
- **THEN** the record is persisted successfully with null installment fields

### Requirement: Categories table model
The system SHALL define a SQLAlchemy ORM model `Category` with fields: `id` (INTEGER, PK, autoincrement), `keyword` (TEXT, not null, unique), `category` (TEXT, not null).

#### Scenario: Category mapping creation
- **WHEN** a Category is created with keyword="全聯" and category="日用品"
- **THEN** the record is persisted and queryable by keyword

#### Scenario: Unique keyword enforcement
- **WHEN** a Category with keyword="全聯" already exists and another with the same keyword is inserted
- **THEN** the database raises an IntegrityError

### Requirement: BankConfigs table model
The system SHALL define a SQLAlchemy ORM model `BankConfig` with fields: `id` (INTEGER, PK, autoincrement), `bank_code` (TEXT, not null, unique), `bank_name` (TEXT, not null), `gmail_filter` (TEXT, not null), `pdf_password_rule` (TEXT, nullable), `active_parser_version` (TEXT, default "v1").

#### Scenario: Bank config creation
- **WHEN** a BankConfig is created with bank_code="CTBC", bank_name="中國信託", gmail_filter="from:service@ctbcbank.com"
- **THEN** the record is persisted with active_parser_version="v1"

### Requirement: Alembic migration support
The system SHALL use Alembic for database migrations. An initial migration SHALL create all 4 tables. The Alembic configuration SHALL point to the SQLite database path from app configuration.

#### Scenario: Initial migration creates all tables
- **WHEN** `alembic upgrade head` is executed against an empty database
- **THEN** tables `bills`, `transactions`, `categories`, and `bank_configs` are created with correct columns and constraints

#### Scenario: Migration is reversible
- **WHEN** `alembic downgrade -1` is executed after the initial migration
- **THEN** all 4 tables are dropped

### Requirement: SQLite WAL mode
The system SHALL configure SQLite to use WAL (Write-Ahead Logging) journal mode for improved read concurrency.

#### Scenario: WAL mode enabled
- **WHEN** a database connection is established
- **THEN** `PRAGMA journal_mode` returns `wal`
