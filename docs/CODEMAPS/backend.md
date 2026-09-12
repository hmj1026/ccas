<!-- Verified: 2026-09-10 | Canonical details: ../current-implementation.md -->

# Backend

> 先看 [目前實作總覽](./current-implementation.md) 取得全局流程；本文件只保留
> API、pipeline stage、設定與後端模組的細節。

## API Routes

All business and setup routes under `/api` require either Bearer token auth or the
HMAC session cookie. Public endpoints are `/health`, `/api/health`, `/health/ready`,
`/api/health/ready`, and `GET/POST /api/auth/session`. Session deletion still
requires valid auth. The Gmail OAuth callback is
also protected; the frontend callback page completes it with the user's session.
Mounted in `api/app.py:create_app()` via `include_router(...)`。

```
Auth (auth.py):
  GET    /api/auth/session                    (公開，檢查瀏覽器 session)
  POST   /api/auth/session                    (公開，以 API token 建立 session)
  DELETE /api/auth/session                    (需有效 Bearer/session)

Dashboard (overview.py):
  GET    /api/overview

Bills (bills.py):
  GET    /api/bills                       (list + paginate)
  GET    /api/bills/payment-due            (agent payment-due projection)
         Requires Bearer/session auth; returns the standard ApiResponse envelope.
  PATCH  /api/bills/{id}                  (mark paid)
  GET    /api/bills/{id}/transactions     (inline transaction list)
  GET    /api/bills/{id}/pdf              (download)

Transactions (transactions.py):
  GET    /api/transactions                (filter, paginate, sort)

Transaction Edit (transactions_edit.py):
  GET    /api/transactions/{id}                       (detail)
  PATCH  /api/transactions/{id}                       (edit category/note/tags/alias → manual_override)
  POST   /api/transactions/{id}/note
  DELETE /api/transactions/{id}/manual-override       (revert to auto-classify)

Exports (exports.py):
  GET    /api/transactions/export         (CSV / Excel — XLSX via openpyxl)

Analytics v1 (analytics.py):
  GET    /api/analytics/years
  GET    /api/analytics/trend
  GET    /api/analytics/categories
  GET    /api/analytics/banks

Analytics v2 (analytics_v2.py — Insights 頁):
  GET    /api/analytics/compare/banks
  GET    /api/analytics/compare/years
  GET    /api/analytics/top-merchants

Settings (settings.py):
  GET    /api/settings/banks
  POST   /api/settings/banks
  PATCH  /api/settings/banks/{id}
  GET    /api/settings/categories
  POST   /api/settings/categories
  PATCH  /api/settings/categories/{id}
  DELETE /api/settings/categories/{id}

Pipeline (pipeline.py):
  POST   /api/pipeline/trigger             (推入 RQ queue → 回傳 run_id)
  GET    /api/pipeline/runs                (status filter + limit ≤100)
  GET    /api/pipeline/runs/{run_id}       (含 stage_summary 詳情)
  GET    /api/pipeline/status              (agent latest-run projection)
         Requires Bearer/session auth; returns the standard ApiResponse envelope.

Rules (rules.py):
  GET    /api/rules                        (filter by enabled)
  POST   /api/rules
  PUT    /api/rules/{id}
  DELETE /api/rules/{id}
  POST   /api/rules/test                   (dry-run pattern + sample matches)

Reminders (reminders_settings.py):
  GET    /api/reminders/settings
  PUT    /api/reminders/{bill_id}/settings (days_before / channel / enabled)
  POST   /api/reminders/{bill_id}/test     (寄送測試訊息)

Budgets (budgets.py):
  GET    /api/budgets                              (list, scope filter)
  POST   /api/budgets
  PUT    /api/budgets/{id}
  DELETE /api/budgets/{id}
  GET    /api/budgets/alerts/active
  POST   /api/budgets/alerts/{id}/acknowledge
  GET    /api/budgets/{id}/current-period          (本期消費 vs 上限)

Staged Attachments (staged_attachments.py):
  GET    /api/staged-attachments           (失敗附件 + status filter)

Setup — Gmail OAuth (setup/gmail.py):
  POST   /api/setup/gmail/credentials      (上傳 client secret JSON)
  GET    /api/setup/gmail/authorize        (取得授權 URL)
  GET    /api/setup/gmail/callback         (OAuth code → token，需有效 Bearer/session)
  GET    /api/setup/gmail/status
  POST   /api/setup/gmail/revoke

Setup — Banks (setup/banks.py):
  GET    /api/setup/banks                  (含 enabled / display_name)
  PUT    /api/setup/banks/{code}

Setup — Bank Secrets (setup/secrets.py):
  GET    /api/setup/secrets                (僅回傳是否已設定)
  PUT    /api/setup/secrets/{code}         (寫入加密的 PDF 密碼)
  DELETE /api/setup/secrets/{code}
  POST   /api/setup/secrets/import-from-env

Setup — Bank Login Credentials (setup/login_credentials.py):
  GET    /api/setup/login-credentials
  PUT    /api/setup/login-credentials/{bank_code}/{credential_key}
  DELETE /api/setup/login-credentials/{bank_code}/{credential_key}
  POST   /api/setup/login-credentials/import-from-env

Setup — Admin Token (setup/admin.py):
  GET    /api/setup/admin/token-info       (rotate 時間 / 版本)
  POST   /api/setup/admin/token-rotate

Health:
  GET    /health                           (no auth)
  GET    /api/health                       (no auth)
  GET    /health/ready                     (DB + Redis readiness)
  GET    /api/health/ready                 (DB + Redis readiness)
```

## Pipeline Stages

`run_pipeline()` in `pipeline/orchestrator.py` 由 RQ worker 執行；progress 透過 `pipeline/progress.py:stage_finished()` 寫入 `PipelineRun.stage_summary`（含 counts + errors），前端 `operations.tsx` 輪詢顯示。
支援 `--from`/`--to` stage range via `PipelineOptions`。

| # | Stage | Module | Key File |
|---|-------|--------|----------|
| 1 | Ingest | `ingestor/` | `job.py`, `gmail_client.py`, `fetcher/`（FUBON web-fetch + captcha） |
| 2 | Decrypt | `decryptor/` | `job.py`, `decrypt.py`；staged_path 以 STAGING_DIR 相對路徑儲存 |
| 3 | Parse | `parser/` | `job.py`, `registry.py`, `banks/{ctbc,esun,taishin,ubot,cathay,sinopac,fubon}_v1.py`, `ocr.py` fallback |
| 4 | Classify | `classifier/` | `job.py`, `engine.py`（先匹配使用者 ClassificationRule，未命中再 keyword） |
| 5 | Notify | `bot/` | `notifications.py`, `job.py`（auto-query is_notified=False） |

## Configuration (config.py Settings)

| Group | Key Fields |
|-------|-----------|
| Database | `database_url`, `staging_dir` |
| Gmail | `gmail_credentials_path`, `gmail_token_path`, `public_base_url`（callback effective path: `/api/setup/gmail/callback`） |
| Telegram | `telegram_bot_token`, `telegram_chat_id`, `telegram_allowed_chat_ids` |
| API | `api_token`, `api_token_path`, `api_token_version_path`, `api_host`, `api_port`, `api_session_cookie_name`, `api_session_max_age`, `api_cookie_secure`, `frontend_origins` |
| Agent | `agent_write_enabled` (default false; no write tools currently exposed) |
| Redis / Queue | `redis_url`（default `redis://localhost:6379/0`） |
| Scheduler | `scheduler_api_base_url`, `scheduler_heartbeat_path`（default `/data/scheduler-heartbeat`） |
| FUBON Fetcher | `fubon_captcha_max_retries`, `fubon_captcha_fallback_llm`, `fubon_captcha_archive_dir`, `fubon_manual_staging_dir`; `FUBON_NATIONAL_ID` / `FUBON_ROC_BIRTHDAY` 由 `get_bank_credential()` 解析 |
| Anthropic | `anthropic_api_key`（SecretStr，僅 captcha LLM fallback 啟用時需要） |
| PDF / Secrets | `pdf_parse_timeout_seconds`, `master_key_path` |
| Logging | `log_level`, `log_format`, `log_dir`, `log_file_max_bytes`, `log_file_backup_count`, `log_file_prefix` |
| PDF Passwords | `get_pdf_password(bank_code)` → 讀 `bank_secrets` 表（fallback `PDF_PASSWORD_{BANK_CODE}`） |
| Database Resilience | `PRAGMA busy_timeout=30000`（per-connection on `connect`）+ `DbProgressReporter.stage_finished` 3-retry backoff（0.1 / 0.5 / 2 秒）on `database is locked` |

## Module Inventory

File and LOC counts are intentionally omitted because they drift quickly. Use the
source tree and the central as-built document for exact current boundaries.

| Module | Key files | Responsibility |
|--------|-----------|----------------|
| `api` | `app.py`, `deps.py`, `routers/`, `schemas/` | FastAPI composition, auth, business and setup endpoints |
| `ingestor` | `job.py`, `gmail_client.py`, `gmail_connection.py`, `fetcher/` | Gmail ingestion, staging, FUBON web-fetch and captcha flow |
| `decryptor` | `job.py`, `decrypt.py` | Resolve bank secrets and decrypt staged PDFs |
| `parser` | `intake.py`, `registry.py`, `banks/`, `ocr.py` | Discover bank/version parser, extract PDF data and persist bills/transactions |
| `classifier` | `job.py`, `engine.py`, `rules.py` | Manual override, user rules, keyword fallback and batch persistence |
| `pipeline` | `orchestrator.py`, `options.py`, `progress.py`, `worker.py` | Stage orchestration, RQ/CLI entry points and run progress |
| `bot` | `job.py`, `notifications.py`, `handlers.py` | Telegram notifications and bot commands |
| `scheduler` | `__main__.py`, `jobs.py`, `reminders.py`, `budget_evaluator.py` | Daily pipeline, reminders, budget evaluation and heartbeat |
| `storage` | `models.py`, `database.py`, `queries.py`, `secrets.py` | ORM models, async sessions, queries and encrypted secrets |
| `services` | `schemas.py`, `bills.py`, `transactions.py`, `budgets.py`, `pipeline.py` | Read-only agent projections shared by REST, CLI and MCP |
| `mcp` | `server.py`, `__main__.py` | Official SDK stdio transport with six read-only tools |
| `cli.py` | `cli.py` | Read-only agent CLI surface |
| `tools` | `bank_configs.py`, `gmail_auth.py`, maintenance scripts | Bank configuration, Gmail helpers and operational utilities |
