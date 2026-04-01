<!-- Generated: 2026-04-01 | Files scanned: 68 | Token estimate: ~800 -->

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

`run_pipeline()` in `pipeline/orchestrator.py` executes sequentially:

| # | Stage | Module | Key File (LOC) |
|---|-------|--------|-----------------|
| 1 | Ingest | `ingestor/` | `job.py` (262), `gmail_client.py` (184) |
| 2 | Decrypt | `decryptor/` | `job.py` (156), `decrypt.py` (68) |
| 3 | Parse | `parser/` | `job.py` (215), `banks/ctbc_v1.py` (191) |
| 4 | Classify | `classifier/` | `job.py` (116), `engine.py` (71) |
| 5 | Notify | `bot/` | `notifications.py` (160), `job.py` (83) |

## Module Inventory

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| api | 12 | 1129 | FastAPI routes, schemas, deps |
| bot | 10 | 892 | Telegram commands, notifications, formatting |
| ingestor | 6 | 736 | Gmail download, staging, retry |
| parser | 8 | 836 | PDF extraction, bank-specific parsers |
| pipeline | 7 | 569 | Orchestrator, worker, CLI, options |
| classifier | 5 | 327 | Keyword engine, rules |
| decryptor | 5 | 306 | PDF password resolution, decryption |
| scheduler | 4 | 237 | APScheduler, reminders |
| storage | 4 | 250 | ORM models, async DB session, queries |
| tools | 3 | 409 | Bank configs (YAML), Gmail auth |
| core | 4 | 330 | config, errors, log, __init__ |
| **Total** | **68** | **~6021** | |
