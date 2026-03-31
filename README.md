# CCAS -- 信用卡帳單自動化系統

自動化信用卡帳單處理流水線：從 Gmail 收取 PDF 帳單、解密、解析交易明細、分類消費類別，最終透過 REST API 儀表板與 Telegram Bot 呈現結果。

## 系統架構

### 資料流

```
Gmail --> staged PDF --> decrypted PDF --> Bill + Transaction[] --> categorized Transaction
                                                |                         |
                                                v                         v
                                          REST API -----------------> React Dashboard
                                                |
                                                v
                                         Telegram Bot <-- payment reminders
```

### Staging 狀態機

```
staged --> decrypted --> parsed       (success path)
  |           |
  v           v
(skipped)  decrypt_failed
              |
              v
           parse_failed
              |
              v
        manual_review_needed    (after 3 retries exhausted)
```

## 技術棧

| 層級 | 技術 |
|------|------|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Database | SQLite (WAL mode) |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Package Manager | uv (backend), pnpm (frontend) |
| Testing | pytest + pytest-cov, httpx (ASGI test client) |
| Linting | ruff (check + format), pyright (type check) |
| Integrations | Gmail API (PDF download), Telegram Bot (notifications) |
| Infrastructure | Docker Compose, Redis (job queue) |

## 快速開始

### 前置需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+ / pnpm
- Docker + Docker Compose (optional, for容器化部署)

### 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入必要值：
- `TELEGRAM_BOT_TOKEN` -- Telegram Bot API token
- `TELEGRAM_CHAT_ID` -- notification target chat ID
- `API_TOKEN` -- API authentication Bearer token
- `PDF_PASSWORD_<BANK_CODE>` -- per-bank PDF decryption passwords

### 後端啟動

```bash
cd backend
uv sync                        # install dependencies
uv run alembic upgrade head    # apply database migrations
uv run fastapi dev             # dev server with hot reload (port 8000)
```

### 前端啟動

```bash
cd frontend
pnpm install                   # install dependencies
pnpm dev                       # dev server (port 5173)
```

### Docker Compose

```bash
docker compose up              # start backend + frontend + Redis
```

## 開發指令

### 後端 (backend/)

```bash
# Testing
uv run pytest                              # all tests
uv run pytest --cov --cov-report=term-missing  # with coverage
uv run pytest tests/unit/                  # unit only
uv run pytest tests/integration/           # integration only
uv run pytest -x                           # stop on first failure

# Lint & Format
uv run ruff check .                        # lint
uv run ruff format .                       # format
uv run pyright                             # type check

# Database
uv run alembic upgrade head                # apply migrations
uv run alembic revision --autogenerate -m "<description>"
```

### 前端 (frontend/)

```bash
pnpm dev                       # dev server
pnpm build                     # production build
pnpm test                      # run tests
pnpm lint                      # lint check
```

## 專案結構

```
ccas/
├── backend/                   # Python FastAPI backend
│   ├── src/ccas/              # application source
│   │   ├── api/               # FastAPI routes & schemas
│   │   ├── ingestor/          # Gmail PDF ingestion
│   │   ├── decryptor/         # PDF decryption
│   │   ├── parser/            # bank statement parsing
│   │   ├── classifier/        # spending classification
│   │   ├── pipeline/          # orchestration & workers
│   │   ├── scheduler/         # job scheduling
│   │   ├── bot/               # Telegram bot
│   │   ├── storage/           # SQLAlchemy models & database
│   │   ├── config.py          # pydantic-settings configuration
│   │   ├── errors.py          # exception hierarchy
│   │   └── log.py             # structured logging
│   ├── tests/                 # unit / integration / e2e
│   ├── alembic/               # database migrations
│   └── pyproject.toml
├── frontend/                  # React + Vite + TypeScript
│   ├── src/
│   │   ├── pages/             # page components
│   │   ├── components/        # shared & UI components
│   │   └── lib/               # utilities
│   └── package.json
├── openspec/                  # OpenSpec workflow artifacts
│   ├── config.yaml            # schema configuration
│   ├── changes/               # active & archived changes
│   └── specs/                 # accepted capability specs
├── docs/                      # project documentation
├── .claude/                   # Claude Code skills & commands
├── .codex/                    # Codex skills
├── .gemini/                   # Gemini skills & commands
├── .env.example               # environment variable template
├── docker-compose.yaml        # container orchestration
├── CLAUDE.md                  # project context (SSOT)
├── AGENTS.md                  # Codex-specific config
└── GEMINI.md                  # Gemini-specific config
```

## OpenSpec 工作流

本專案使用 [OpenSpec](https://github.com/anthropics/openspec) 進行 spec-driven 開發。工作流程：

```
proposal -> specs -> design -> tasks -> implementation -> archive
```

詳細的實作階段與相依關係，請參考 [docs/EXECUTION_ORDER.md](docs/EXECUTION_ORDER.md)。
