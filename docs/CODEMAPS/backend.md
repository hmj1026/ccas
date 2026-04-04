<!-- Generated: 2026-04-04 | Files scanned: 69 | Token estimate: ~800 -->

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
| 1 | Ingest | `ingestor/` | `job.py`, `gmail_client.py` |
| 2 | Decrypt | `decryptor/` | `job.py`, `decrypt.py` |
| 3 | Parse | `parser/` | `job.py`, `banks/ctbc_v1.py`, `ocr.py` (fallback) |
| 4 | Classify | `classifier/` | `job.py`, `engine.py` |
| 5 | Notify | `bot/` | `notifications.py`, `job.py` (auto-query is_notified=False) |

## Module Inventory

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| api | 12 | 1163 | FastAPI routes, schemas, deps, security headers middleware |
| parser | 9 | 1192 | PDF extraction, bank parsers, OCR fallback (pytesseract), non-transaction filtering |
| bot | 10 | 900 | Telegram commands, notifications, auto-query pending bills (is_notified=False) |
| ingestor | 6 | 736 | Gmail download, staging, retry |
| pipeline | 7 | 637 | Orchestrator, worker, CLI, options, stage range |
| tools | 3 | 409 | Bank configs (YAML), Gmail auth |
| classifier | 5 | 327 | Keyword engine, rules |
| decryptor | 5 | 308 | PDF password resolution, decryption |
| storage | 4 | 251 | ORM models, async DB session, queries |
| scheduler | 4 | 237 | APScheduler, reminders |
| core | 4 | 330 | config, errors, log, __init__ |
| **Total** | **69** | **~6490** | |
