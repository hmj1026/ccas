---
name: ccas-tech-stack
description: "CCAS 專案技術棧總覽。使用時機：新人 onboarding、架構討論、評估技術選型、使用者詢問「這專案用什麼技術」、或需要判斷某個工具/框架是否屬於本專案 stack 時。不含開發指令（見 ccas-dev-commands）與環境設定（見 ccas-env-config）。"
---

# CCAS 技術棧

CCAS（Credit Card Automation System）是一套信用卡帳單自動化 pipeline：從 Gmail 擷取 PDF 帳單 → 解密 → 解析 → 消費分類 → 透過 REST API dashboard 與 Telegram 通知。

## 主要技術

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | SQLite (WAL mode) via aiosqlite |
| Frontend | React 19, Vite, TypeScript 5.9, Tailwind CSS 4, shadcn/ui |
| State / Data | TanStack React Query v5, React Router v7 |
| Package Manager | uv (backend), pnpm (frontend) |
| Testing | pytest + pytest-asyncio + pytest-cov (>80% 硬性), httpx (ASGI test client), Vitest (frontend) |
| Linting | ruff (check + format), pyright (strict), ESLint |
| Job Queue | rq + redis, APScheduler |
| Document Parsing | pdfplumber, pikepdf, tabula-py, pytesseract (OCR) |
| Integrations | Gmail API（PDF 下載）, Telegram Bot（通知） |
| Deploy | docker-compose（7 services：backend / worker / scheduler / bot / frontend / redis / dev-tools） |
| Spec | OpenSpec（外部 CLI，spec-driven workflow） |
| Domain | 信用卡帳單自動化（PDF 解析、消費分類、報表） |

## 架構特點

- **Async-first**：FastAPI + SQLAlchemy async ORM + asyncio fixtures 貫穿整個 stack
- **Registry Pattern**：多銀行 parser 透過 registry 多型載入（CTBC、Cathay、Sinopac、Fubon、Esun、Taishin、Ubot）
- **Layered pipeline**：api → pipeline orchestrator → 專門化 stages（ingestor → decryptor → parser → classifier → notifier）
- **Dependency Injection**：FastAPI `Depends()` 管理 auth / DB session / settings
- **Test Pyramid**：unit（純邏輯）→ integration（in-memory SQLite + ASGI client）→ e2e（完整 pipeline）

## Backend 模組結構（`backend/src/ccas/`）

- `api/` — FastAPI routes（bills / transactions / analytics / overview / settings），Bearer token auth
- `pipeline/` — orchestrator、worker、filters、summary
- `parser/` — registry-based 多銀行 statement parsers
- `classifier/` — 交易分類引擎
- `ingestor/` — Gmail client、staging、auth、retry
- `decryptor/` — 加密 PDF 解密
- `bot/` — Telegram bot
- `scheduler/` — APScheduler 排程與提醒
- `storage/` — SQLAlchemy models、DB session
- `tools/` — bank configs、Gmail auth helpers
- `config.py` — Pydantic Settings 環境導向設定

## Frontend 結構（`frontend/src/`）

- `pages/` — bills / transactions / analytics / overview / settings / login
- `components/` — auth-guard、layout
- `lib/` — API client、types、utilities

## 外部依賴（不 vendor、不手動同步）

- **OpenSpec CLI** — 外部套件，wrapper skills 在 `.claude/skills/openspec-*/`
- **ECC plugin**（`everything-claude-code`）— 提供全域 skills（python-patterns / tdd-workflow / python-reviewer 等）
- **codex plugin** / **pyright-lsp plugin** — 透過 `.claude/settings.json` `enabledPlugins` 啟用
