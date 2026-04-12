<!-- Generated: 2026-04-12 | Files scanned: ~90 | Token estimate: ~650 -->

# Architecture

## System Overview

Credit card bill automation: ingest PDF statements from Gmail, decrypt, parse, classify spending, expose via REST API + Telegram bot.

## Data Flow

```
Gmail ──┐
        ├─> Ingestor ──> Decryptor ──> Parser ──> Classifier ──> Notifier
Web   ──┘   (+ fetcher/)  (pikepdf)   (pdfplumber) (keyword)    (Telegram)
             │                        + OCR          │
             v                           │           v
        StagedAttachment            Bill + Txn     category field
        (status + source_type)       (SQLite)
```

`ingestor/fetcher/` 提供 Gmail 以外的來源（目前：FUBON 網銀 web-fetch + captcha）。
`staged_attachments.source_type` 區分 `gmail` / `web`；dedupe 依 `(gmail_message_id, gmail_part_id)`。

## Entry Points

| Entry | Module | Command |
|-------|--------|---------|
| REST API | `ccas.api.app:create_app()` | `uv run uvicorn ccas.api.app:create_app --factory` |
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
| Testing | pytest + pytest-cov (80% min), Vitest |
| External | Gmail API, Telegram Bot API, Redis (job queue) |
| Infra | Docker Compose |

## Module Map

```
backend/src/ccas/
├── api/          REST endpoints (FastAPI) + security headers middleware
├── bot/          Telegram bot commands & notifications
├── classifier/   Transaction categorization
├── decryptor/    PDF password decryption
├── ingestor/     Gmail PDF download & staging; `fetcher/` web scrapers (FUBON + captcha)
├── parser/       PDF extraction for 7 banks (CTBC/ESUN/Taishin/UBOT/Cathay/SinoPac/Fubon) + OCR fallback
├── pipeline/     5-stage orchestrator with stage range control (--from/--to)
├── scheduler/    APScheduler cron jobs
├── storage/      SQLAlchemy models, database, queries
├── tools/        Bank configs, Gmail auth helpers
├── config.py     Pydantic Settings
├── errors.py     Exception hierarchy
└── log.py        Structured JSON logging
```
