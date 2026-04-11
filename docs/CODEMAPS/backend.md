<!-- Generated: 2026-04-11 | Files scanned: 78 | Token estimate: ~950 -->

# Backend

## API Routes

All under `/api`, require Bearer token auth (except `/health`).

```
Auth:
  GET    /session              auth.py
  POST   /session              auth.py
  DELETE /session              auth.py

Dashboard:
  GET    /overview             overview.py

Bills:
  GET    /bills                bills.py
  PATCH  /bills/{id}           bills.py (mark paid)
  GET    /bills/{id}/pdf       bills.py (download)

Transactions:
  GET    /transactions         transactions.py (filter, paginate, sort)
  GET    /transactions/export  transactions.py (CSV/Excel)

Analytics:
  GET    /analytics/years      analytics.py (available years)
  GET    /analytics/trend      analytics.py (by category/month)
  GET    /analytics/categories analytics.py (breakdown)
  GET    /analytics/banks      analytics.py (per-bank)

Settings:
  GET    /settings/banks       settings.py
  POST   /settings/banks       settings.py
  PATCH  /settings/banks/{id}  settings.py
  GET    /settings/categories  settings.py
  POST   /settings/categories  settings.py
  PATCH  /settings/categories/{id}  settings.py
  DELETE /settings/categories/{id}  settings.py

Pipeline:
  POST   /api/pipeline/trigger pipeline.py

Health:
  GET    /health               app.py (no auth)
```

## Pipeline Stages

`run_pipeline()` in `pipeline/orchestrator.py` executes sequentially.
Supports `--from`/`--to` stage range via `PipelineOptions`.

| # | Stage | Module | Key File (LOC) |
|---|-------|--------|-----------------|
| 1 | Ingest | `ingestor/` | `job.py`, `gmail_client.py`, `fetcher/` (web scrapers) |
| 2 | Decrypt | `decryptor/` | `job.py`, `decrypt.py` |
| 3 | Parse | `parser/` | `job.py`, `registry.py`, `banks/{ctbc,esun,taishin,ubot,cathay,sinopac,fubon}_v1.py`, `ocr.py` (fallback) |
| 4 | Classify | `classifier/` | `job.py`, `engine.py` |
| 5 | Notify | `bot/` | `notifications.py`, `job.py` (auto-query is_notified=False) |

## Configuration (config.py Settings)

| Group | Key Fields |
|-------|-----------|
| Database | `database_url`, `staging_dir` |
| Gmail | `gmail_credentials_path`, `gmail_token_path` |
| Telegram | `telegram_bot_token`, `telegram_chat_id`, `telegram_allowed_chat_ids` |
| API | `api_token`, `api_host`, `api_port`, `api_session_cookie_name`, `api_session_max_age`, `api_cookie_secure`, `frontend_origins` |
| Redis | `redis_url` (default: `redis://localhost:6379/0`) |
| Scheduler | `scheduler_api_base_url` |
| Logging | `log_level`, `log_format`, `log_dir`, `log_file_max_bytes`, `log_file_backup_count`, `log_file_prefix` |
| PDF Passwords | `get_pdf_password(bank_code)` → reads `PDF_PASSWORD_{BANK_CODE}` env var |

## Module Inventory

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| api | 12 | 1310 | FastAPI routes, schemas, deps, security headers middleware |
| parser | 15 | 4342 | 7 bank parsers (CTBC/ESUN/Taishin/UBOT/Cathay/SinoPac/Fubon), registry, result, OCR fallback |
| ingestor | 13 | 1395 | Gmail download + staging + retry; `fetcher/` sub-module (web scrapers, captcha, FUBON bank) |
| bot | 10 | 932 | Telegram commands, notifications, auto-query pending bills (is_notified=False) |
| pipeline | 7 | 637 | Orchestrator, worker, CLI, options, stage range |
| tools | 3 | 409 | Bank configs (YAML), Gmail auth |
| classifier | 5 | 327 | Keyword engine, rules |
| decryptor | 5 | 308 | PDF password resolution, decryption |
| storage | 4 | 256 | ORM models, async DB session, queries |
| scheduler | 4 | 245 | APScheduler, reminders |
| core | 4 | 330 | config, errors, log, __init__ |
| **Total** | **82** | **~10491** | |
