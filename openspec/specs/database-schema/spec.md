# database-schema Specification

## Purpose
TBD - created by archiving change foundation-setup. Update Purpose after archive.
## Requirements
### Requirement: 帳單主表資料模型

系統 SHALL 維持 `Bill` 資料模型的既有欄位與唯一約束，新增 `is_notified` 欄位追蹤通知狀態，且 `created_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### MODIFIED Scenario: 建立帳單紀錄
- **WHEN** 建立一筆 `Bill`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime（`datetime.now(UTC)`），而非 naive datetime

#### ADDED Scenario: 新帳單預設未通知
- **WHEN** 建立新的 Bill 記錄
- **THEN** `is_notified` SHALL 預設為 `False`

#### ADDED Scenario: 既有帳單視為已通知
- **WHEN** Alembic migration 套用至既有資料庫
- **THEN** 所有現有 Bill 的 `is_notified` SHALL 設為 `True`（避免舊帳單重發通知）

### Requirement: 消費明細資料表模型

系統 SHALL 維持 `Transaction` 資料模型的既有欄位與外鍵關聯，且 `created_at` 的 Python 端預設值 SHALL 由 naive `datetime.utcnow()` 改為 timezone-aware 的 `datetime.now(UTC)`。

#### MODIFIED Scenario: 消費明細可連結到帳單
- **WHEN** 建立一筆具有有效 `bill_id` 的 `Transaction`
- **THEN** `created_at` 會自動設定為 timezone-aware UTC datetime

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
