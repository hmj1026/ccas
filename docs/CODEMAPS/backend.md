<!-- Generated: 2026-04-01 | Files scanned: 67 | Token estimate: ~800 -->

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
| api | 10 | 584 | FastAPI routes, schemas, deps |
| bot | 8 | 883 | Telegram commands, notifications, formatting |
| ingestor | 5 | 727 | Gmail download, staging, retry |
| parser | 6 | 791 | PDF extraction, bank-specific parsers |
| pipeline | 6 | 553 | Orchestrator, worker, CLI, options |
| classifier | 4 | 322 | Keyword engine, rules |
| decryptor | 4 | 298 | PDF password resolution, decryption |
| scheduler | 3 | 243 | APScheduler, reminders |
| storage | 2 | 227 | ORM models, async DB session |
| tools | 2 | 405 | Bank configs (YAML), Gmail auth |
| core | 4 | 325 | config, errors, log, __init__ |
| **Total** | **67** | **~6000** | |
