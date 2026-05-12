<!-- Generated: 2026-05-10 | Files scanned: ~95 | Token estimate: ~760 -->

# Architecture

## System Overview

Credit card bill automation: ingest PDF statements from Gmail（或銀行網銀 web-fetch）, decrypt, parse, classify spending, expose via REST API + Telegram bot。新增 pipeline-operations-center 提供 UI 觸發 + 進度追蹤、bills-management-and-insights 提供分類規則 / 預算 / 提醒設定 / insights v2。

## Data Flow

```
Gmail ──┐
        ├─> Ingestor ──> Decryptor ──> Parser ──> Classifier ──> Notifier
Web   ──┘   (+ fetcher/)  (pikepdf)   (pdfplumber)  ↑↓ rules    (Telegram)
             │                        + OCR         │           │
             v                          │           v           v
        StagedAttachment            Bill + Txn   ClassificationRule
        (status + source_type)       (SQLite)    (priority + pattern)
                                        │
                                        v
                                Budget / BudgetAlert
                                ReminderSetting
```

`ingestor/fetcher/` 提供 Gmail 以外的來源（目前：FUBON 網銀 web-fetch + captcha）。
`staged_attachments.source_type` 區分 `gmail` / `web`；dedupe 依 `(gmail_message_id, gmail_part_id)`。
Pipeline 由 `/api/pipeline/trigger` 推入 RQ queue；`PipelineRun` 紀錄 stage 進度（`current_stage`、`stage_summary`），前端 `operations.tsx` 輪詢 `/runs`。
分類引擎優先比對使用者 `ClassificationRule`（priority DESC），未命中再 fallback 到 keyword seed。

## Entry Points

| Entry | Module | Command |
|-------|--------|---------|
| REST API | `ccas.api.app:create_app()` | `uv run uvicorn ccas.api.app:create_app --factory` |
| Pipeline CLI | `ccas.pipeline.__main__:main()` | `uv run python -m ccas.pipeline` |
| RQ Worker | `rq worker` | `uv run rq worker --url $REDIS_URL`（rq 2.x，已不再支援 `--quiet`） |
| Scheduler | `ccas.scheduler.__main__:main()` | `uv run python -m ccas.scheduler`（寫 heartbeat 至 `SCHEDULER_HEARTBEAT_PATH=/data/scheduler-heartbeat`） |
| Telegram Bot | `ccas.bot.__main__:main()` | `uv run python -m ccas.bot` |
| Frontend | Vite SPA → nginx | `pnpm dev` (local) / Docker `frontend` service |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async) |
| Database | SQLite + aiosqlite (WAL mode) |
| Migrations | Alembic（含 SQLite trigger 維護 `updated_at`） |
| Job Queue | Redis + RQ 2.x |
| Frontend | React 19, Vite 8, TypeScript 5.9, Tailwind 4.2, shadcn |
| Package Mgmt | uv (backend), pnpm (frontend) |
| Linting | ruff (lint+format), pyright (types) |
| Testing | pytest + pytest-cov + pytest-timeout (80% min), Vitest, Playwright e2e |
| External | Gmail API, Telegram Bot API, Anthropic API（FUBON captcha LLM fallback） |
| Infra | Docker Compose（backend/worker/scheduler/bot/frontend/redis） |

## Module Map

```
backend/src/ccas/
├── api/          FastAPI app + 18 routers（含 setup/ 子目錄 4 routers）+ schemas
├── bot/          Telegram bot commands & notifications
├── classifier/   Transaction categorization（user rules 優先，keyword fallback）
├── decryptor/    PDF password decryption
├── ingestor/     Gmail PDF download & staging；`fetcher/` web scrapers (FUBON + captcha)
├── parser/       PDF extraction for 7 banks + OCR fallback
├── pipeline/     orchestrator + progress + RQ jobs（PipelineRun 寫入 stage_summary）
├── scheduler/    APScheduler cron + reminder dispatch + heartbeat writer
├── storage/      SQLAlchemy models + repos
├── tools/        Bank configs YAML、Gmail auth、reclassify utility
├── config.py     pydantic-settings (.env)
├── errors.py     CcasError hierarchy
└── log.py        Structured JSON logging
```

```
frontend/src/
├── pages/        12 routes（/insights /operations /setup/* /settings/{rules,budgets,reminders} 等）
├── components/   shared + ui（含 budget / comparison / export / top-merchants 等元件）
└── lib/          api-client + types
```

## OpenSpec Changes (2026-04-22 → 2026-05-10)

| Change | 主要產物 |
|--------|---------|
| `bills-management-and-insights` (D1+D2) | analytics_v2、exports、insights、reminders、budgets、rules、transaction edit |
| `pipeline-operations-center` | pipeline router、PipelineRun、operations 頁、stage_finished propagation |
| `compose-pull-deploy` | release artifact upload、scheduler heartbeat、worker rq 2.x flag、SSOT clean-dir verify |
| `sqlite-busy-timeout-retry`（PR #6 / #11） | `PRAGMA busy_timeout=30000`（per-connection）+ `stage_finished` 3-retry backoff（0.1 / 0.5 / 2 秒）on `database is locked` |
| `scheduler-heartbeat-polish`（PR #9 / #10） | Path-typed Settings + tolerant OSError init；`SCHEDULER_HEARTBEAT_PATH` 由 30 秒 interval job 自動補寫 |
