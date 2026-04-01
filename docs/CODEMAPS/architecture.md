<!-- Generated: 2026-04-01 | Files scanned: 90 | Token estimate: ~600 -->

# Architecture

## System Overview

Credit card bill automation: ingest PDF statements from Gmail, decrypt, parse, classify spending, expose via REST API + Telegram bot.

## Data Flow

```
Gmail ──> Ingestor ──> Decryptor ──> Parser ──> Classifier ──> Notifier
           (PDF)       (pikepdf)    (pdfplumber)  (keyword)    (Telegram)
             │                          │              │
             v                          v              v
        StagedAttachment           Bill + Transaction  category field
           (status tracking)        (SQLite)           (updated)
```

## Entry Points

| Entry | Module | Command |
|-------|--------|---------|
| REST API | `ccas.api.app:create_app()` | `uv run fastapi dev` |
| Pipeline CLI | `ccas.pipeline.__main__:main()` | `uv run python -m ccas.pipeline` |
| Scheduler | `ccas.scheduler.__main__:main()` | `uv run python -m ccas.scheduler` |
| Telegram Bot | `ccas.bot.__main__:main()` | `uv run python -m ccas.bot` |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) |
| Database | SQLite + aiosqlite (WAL mode) |
| Migrations | Alembic |
| Frontend | React 19, Vite 8, TypeScript, Tailwind, shadcn |
| Package Mgmt | uv (backend), pnpm (frontend) |
| Linting | ruff (lint+format), pyright (types) |
| Testing | pytest + pytest-cov, Vitest |
| External | Gmail API, Telegram Bot API, Redis (job queue) |
| Infra | Docker Compose |

## Module Map

```
backend/src/ccas/
├── api/          REST endpoints (FastAPI)
├── bot/          Telegram bot commands & notifications
├── classifier/   Transaction categorization
├── decryptor/    PDF password decryption
├── ingestor/     Gmail PDF download & staging
├── parser/       PDF table extraction (bank-specific)
├── pipeline/     5-stage orchestrator
├── scheduler/    APScheduler cron jobs
├── storage/      SQLAlchemy models + database
├── tools/        Bank configs, Gmail auth helpers
├── config.py     Pydantic Settings
├── errors.py     Exception hierarchy
└── log.py        Structured JSON logging
```
