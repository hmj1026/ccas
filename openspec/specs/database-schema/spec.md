# database-schema Specification

## Purpose
TBD - created by archiving change foundation-setup. Update Purpose after archive.
## Requirements
### Requirement: 帳單主表資料模型
系統 SHALL 定義一個 SQLAlchemy ORM model `Bill`，欄位包含：`id`（INTEGER, PK, autoincrement）、`bank_code`（TEXT, not null）、`billing_month`（TEXT, not null, 格式 `YYYY-MM`）、`total_amount`（INTEGER, not null）、`due_date`（DATE, not null）、`is_paid`（BOOLEAN, 預設 false）、`file_path`（TEXT）、`created_at`（DATETIME, 預設 `utcnow`）。系統 SHALL 在 (`bank_code`, `billing_month`) 上建立唯一約束。

#### Scenario: 建立帳單紀錄
- **WHEN** 建立一筆 `Bill`，內容為 `bank_code="CTBC"`、`billing_month="2026-03"`、`total_amount=15000`、`due_date="2026-04-15"`
- **THEN** 該紀錄會成功持久化，且 `is_paid=false`、`created_at` 會自動設定

#### Scenario: 防止重複帳單
- **WHEN** 已存在一筆 `bank_code="CTBC"` 且 `billing_month="2026-03"` 的 `Bill`，又插入另一筆相同組合資料
- **THEN** 資料庫會拋出 `IntegrityError`

### Requirement: 消費明細資料表模型
系統 SHALL 定義一個 SQLAlchemy ORM model `Transaction`，欄位包含：`id`（INTEGER, PK, autoincrement）、`bill_id`（INTEGER, FK 至 `bills.id`, not null）、`trans_date`（DATE, not null）、`posting_date`（DATE, nullable）、`merchant`（TEXT, not null）、`amount`（INTEGER, not null）、`currency`（TEXT, 預設 `"TWD"`）、`original_amount`（INTEGER, nullable）、`card_last4`（TEXT, nullable）、`installment_current`（INTEGER, nullable）、`installment_total`（INTEGER, nullable）、`category`（TEXT, nullable）、`note`（TEXT, nullable）、`created_at`（DATETIME, 預設 `utcnow`）。

#### Scenario: 消費明細可連結到帳單
- **WHEN** 建立一筆具有有效 `bill_id` 的 `Transaction`
- **THEN** 該紀錄會成功持久化，且可透過 `bill.transactions` relationship 存取

#### Scenario: 外鍵約束生效
- **WHEN** 建立一筆 `bill_id` 不存在於 `bills` 的 `Transaction`
- **THEN** 資料庫會拋出 `IntegrityError`

#### Scenario: 分期欄位可為空值
- **WHEN** 建立一筆非分期的 `Transaction`，並將 `installment_current=None` 與 `installment_total=None`
- **THEN** 該紀錄會成功持久化，且分期欄位以 null 保存

### Requirement: 分類對應資料表模型
系統 SHALL 定義一個 SQLAlchemy ORM model `Category`，欄位包含：`id`（INTEGER, PK, autoincrement）、`keyword`（TEXT, not null, unique）、`category`（TEXT, not null）。

#### Scenario: 建立分類對應
- **WHEN** 建立一筆 `Category`，內容為 `keyword="全聯"`、`category="日用品"`
- **THEN** 該紀錄會成功持久化，且可透過 `keyword` 查詢

#### Scenario: 關鍵字唯一約束生效
- **WHEN** 已存在 `keyword="全聯"` 的 `Category`，又插入另一筆相同 `keyword`
- **THEN** 資料庫會拋出 `IntegrityError`

### Requirement: 銀行設定資料表模型
系統 SHALL 定義一個 SQLAlchemy ORM model `BankConfig`，欄位包含：`id`（INTEGER, PK, autoincrement）、`bank_code`（TEXT, not null, unique）、`bank_name`（TEXT, not null）、`gmail_filter`（TEXT, not null）、`pdf_password_rule`（TEXT, nullable）、`active_parser_version`（TEXT, 預設 `"v1"`）、`is_active`（BOOLEAN, 預設 true）。

#### Scenario: 建立銀行設定
- **WHEN** 建立一筆 `BankConfig`，內容為 `bank_code="CTBC"`、`bank_name="中國信託"`、`gmail_filter="from:service@ctbcbank.com"`
- **THEN** 該紀錄會成功持久化，且 `active_parser_version="v1"`、`is_active=true`

#### Scenario: 可停用銀行設定
- **WHEN** 某筆 `BankConfig` 被標記為 `is_active=false`
- **THEN** 後續流程可以辨識該銀行設定已停用，並在需要時略過處理

### Requirement: 支援 Alembic migration
系統 SHALL 使用 Alembic 管理資料庫 migration。初始 migration SHALL 建立上述 4 個資料表，且 Alembic 設定 SHALL 指向來自 app configuration 的 SQLite 資料庫路徑。

#### Scenario: 初始 migration 建立所有資料表
- **WHEN** 對空白資料庫執行 `alembic upgrade head`
- **THEN** `bills`、`transactions`、`categories`、`bank_configs` 4 個資料表都會以正確欄位與約束建立

#### Scenario: Migration 可逆轉
- **WHEN** 初始 migration 套用後執行 `alembic downgrade -1`
- **THEN** 上述 4 個資料表都會被移除

### Requirement: 使用 Async SQLAlchemy Engine
系統 SHALL 使用 `sqlalchemy[asyncio]` 與 `aiosqlite` 建立非同步資料庫引擎。SQLAlchemy session 製造工廠 SHALL 透過 `async_sessionmaker()` 定義，所有 DB query 都應使用 `async with` 語法。

#### Scenario: 建立 async engine
- **WHEN** 應用程式啟動時初始化資料庫
- **THEN** engine 會以 `create_async_engine("sqlite+aiosqlite://...")` 建立

#### Scenario: 使用 async session
- **WHEN** 在 FastAPI route 中取得 DB session dependency
- **THEN** session 會是 async session，所有 query 應使用 `await` 與 `async with`

### Requirement: 啟用 SQLite WAL mode
系統 SHALL 將 SQLite 設定為 WAL（Write-Ahead Logging）journal mode，以提升讀取並行性。此設定應在 engine creation 時透過 `connect_args` 與 event listener 設定。

#### Scenario: 啟用 WAL mode
- **WHEN** 建立資料庫連線時
- **THEN** 引擎會自動透過 `sqlite_synchronous` pragma 啟用 WAL，`PRAGMA journal_mode` 會回傳 `wal`

