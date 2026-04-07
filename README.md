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

給第一次接觸這個專案的人，建議先看完整教學：

- [開發者指南](docs/developer-guide.md)
- [Bank Code 對照表](docs/bank-codes.md)

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

<!-- AUTO-GENERATED from .env.example -->
| 變數 | 必填 | 說明 | 預設值 |
|------|------|------|--------|
| **資料庫** | | | |
| `DATABASE_URL` | 否 | SQLite 連線字串 | `sqlite+aiosqlite:///./data/ccas.db` |
| **Telegram** | | | |
| `TELEGRAM_BOT_TOKEN` | 是* | Bot API token（從 @BotFather 取得）| — |
| `TELEGRAM_CHAT_ID` | 是* | 通知目標 chat ID | — |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 是* | Bot 指令白名單（逗號分隔）| — |
| **Gmail** | | | |
| `GMAIL_CREDENTIALS_PATH` | 否 | OAuth credentials.json 路徑 | `./data/credentials.json` |
| `GMAIL_TOKEN_PATH` | 否 | OAuth token.json 路徑 | `./data/token.json` |
| `STAGING_DIR` | 否 | PDF staging 目錄 | `./data/staging` |
| **API** | | | |
| `API_TOKEN` | **是** | Bearer token（登入用）| — |
| `API_HOST` | 否 | 監聽 host | `0.0.0.0` |
| `API_PORT` | 否 | 監聽 port | `8000` |
| `FRONTEND_ORIGINS` | 否 | CORS allowed origins | `http://127.0.0.1:5173,...` |
| **Redis** | | | |
| `REDIS_URL` | 否 | Redis 連線字串（prod 需修改）| `redis://localhost:6379/0` |
| **排程器** | | | |
| `SCHEDULER_API_BASE_URL` | 否 | 排程器呼叫 API 的 base URL | `http://127.0.0.1:{API_PORT}` |
| **日誌** | | | |
| `LOG_LEVEL` | 否 | 日誌等級 | `INFO` |
| `LOG_FORMAT` | 否 | 輸出格式（`json` / `text`）| `json` |
| `LOG_DIR` | 否 | 日誌檔案目錄（空 = 僅 stdout）| — |
| **帳單 PDF 密碼** | | | |
| `PDF_PASSWORD_<BANK_CODE>` | 是* | 各銀行 PDF 解密密碼 | — |

*依實際需求填入；留空時對應功能停用。
<!-- AUTO-GENERATED END -->

### 後端啟動

```bash
cp config/banks.example.yaml config/banks.yaml
./scripts/setup.sh
./scripts/start.sh
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

## CI/CD

<!-- AUTO-GENERATED from .github/workflows/ci.yaml -->
**觸發條件**：push 或 Pull Request 至 `develop` / `master`

| Job | 內容 |
|-----|------|
| `backend-lint` | `ruff check` lint、`ruff format --check` 格式檢查、`pyright` 型別檢查 |
| `backend-test` | `pytest tests/unit/` 單元測試（coverage ≥ 70%） |
| `frontend-lint-test` | `pnpm lint` + `pnpm build`（含 TypeScript 檢查）+ `pnpm test` |

工具鏈：`astral-sh/setup-uv@v4`、Python 3.12、`uv sync --frozen --all-extras`（後端）；`pnpm/action-setup@v4`、Node.js 22（前端）
<!-- AUTO-GENERATED END -->

## OpenSpec 工作流

本專案使用 [OpenSpec](https://github.com/anthropics/openspec) 進行 spec-driven 開發。工作流程：

```
proposal -> specs -> design -> tasks -> implementation -> archive
```
