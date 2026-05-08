# CCAS -- 信用卡帳單自動化系統

自動化信用卡帳單處理流水線：從 Gmail 收取 PDF 帳單、解密、解析交易明細、分類消費類別，最終透過 REST API 儀表板與 Telegram Bot 呈現結果。

## 快速安裝（Docker Compose）

> 請先依 [Gmail OAuth 設定](docs/gmail-setup.md) 建立 OAuth client 並下載 `credentials.json`。服務啟動後可在 `/setup/gmail` 上傳並完成授權。

```bash
mkdir ~/ccas && cd ~/ccas
RELEASE=v0.1.0   # 改為要安裝的精確版號
curl -fsSL -o docker-compose.yml \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/docker-compose.yml"
curl -fsSL -o example.env \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/example.env"
cp example.env .env
# 編輯 .env：填入 REPO_OWNER、CCAS_VERSION；PDF 密碼可稍後在 /setup/secrets 設定
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

啟動後：
1. 取得登入 token：`cat ./data/secrets/api-token`
2. 瀏覽器開 `http://localhost:8080/login`，貼上 token 即可進入 dashboard
3. 進「設定中心」完成 Gmail、銀行啟用、PDF 密碼與 token 管理

完整步驟（含每個變數說明、設定中心與進階 fallback）見
[docs/install-quickstart.md](docs/install-quickstart.md)。
升級流程見 [docs/upgrade-guide.md](docs/upgrade-guide.md)。

## 個人帳務管理

`bills-management-and-insights` 提供：

- **交易編輯**：在 `/transactions/{id}` 手動改類別（建立 manual override，pipeline 不會覆寫）、備註、標籤、商家別名
- **個人分類規則**：`/settings/rules` keyword / exact / regex 三種 pattern + priority + 即時規則測試；含 100ms regex timeout fail-soft 與 nested quantifier 警示
- **付款提醒**：`/settings/reminders` 為每筆未付帳單設定 `enabled / days_before / channel`（telegram / ui_banner / both）+ 一鍵測試
- **預算告警**：`/settings/budgets` 三種 scope（每月總額 / 單類別 / 單銀行）+ 80% / 100% 兩階 Telegram 推播 + overview banner
- **Insights**：`/insights` 含月趨勢、銀行對比、年度對比、商家排行、類別 vs 上月
- **匯出**：CSV / xlsx 串流匯出，支援日期 / 銀行 / 類別 filter 及 `include_user_fields`

詳細操作流程、API 範例與規則 best practice 見 [docs/personal-rules-and-budgets.md](docs/personal-rules-and-budgets.md)。

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

## 透過 AI 協助安裝

不熟悉命令列或想省去查文件的時間？複製下方提示詞，貼入 Claude、ChatGPT 或任何 AI 聊天介面，AI 會閱讀 [`docs/ai-setup-guide.md`](docs/ai-setup-guide.md) 並一步一步引導你完成所有設定。

````
我想在本地安裝 CCAS 信用卡帳單自動化系統。
這個系統會自動從 Gmail 收取信用卡帳單 PDF、解析交易明細、分類消費，
並可透過 Telegram Bot 接收帳單提醒，以及透過前端儀表板查看整理後的信用卡資訊。

請先閱讀以下安裝引導文件的內容（docs/ai-setup-guide.md），然後：
1. 先詢問我的作業系統、是否已安裝 Docker、使用哪些銀行信用卡、是否需要 Telegram Bot
2. 根據我的回答決定安裝路線
3. 一個步驟確認完成再進行下一步

---

[將 docs/ai-setup-guide.md 的全部內容貼在此處]
````

> 使用方式：先用文字編輯器開啟 `docs/ai-setup-guide.md`，複製全部內容，貼入上方 `[將 docs/ai-setup-guide.md 的全部內容貼在此處]` 的位置，再把整段文字送給 AI。

---

## 快速開始

給第一次接觸這個專案的人，先依角色挑選對應文件：

- **開發者**：[開發者指南](docs/developer-guide.md) — 本地環境設定、uv/pnpm、alembic、seed
- **非開發使用者**：[使用者操作手冊](docs/user-guide.md) — Docker Compose 啟動、Gmail／Telegram 設定
- **部署／維運**：[部署指南](docs/deployment-guide.md)、[維運 Runbook](docs/RUNBOOK.md)
- **QA 測試**：[QA 測試指南](docs/qa-testing-guide.md)
- **貢獻者**：[CONTRIBUTING.md](docs/CONTRIBUTING.md) — 分支策略、commit 規範、pre-commit hook
- **參考**：[Bank Code 對照表](docs/bank-codes.md)、[產品方向 SSOT](docs/notion.md)
- **架構地圖**：見下方 [「文件索引」](#文件索引) 段落的 `docs/CODEMAPS/`

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
| **Session** | | | |
| `API_SESSION_COOKIE_NAME` | 否 | Session cookie 名稱 | `ccas_session` |
| `API_SESSION_MAX_AGE` | 否 | Session 有效秒數 | `43200` |
| `API_COOKIE_SECURE` | 否 | 僅允許 HTTPS 傳送 cookie | `False` |
| **Redis** | | | |
| `REDIS_URL` | 否 | Redis 連線字串（prod 需修改）| `redis://localhost:6379/0` |
| **排程器** | | | |
| `SCHEDULER_API_BASE_URL` | 否 | 排程器呼叫 API 的 base URL | `http://127.0.0.1:{API_PORT}` |
| **日誌** | | | |
| `LOG_LEVEL` | 否 | 日誌等級 | `INFO` |
| `LOG_FORMAT` | 否 | 輸出格式（`json` / `text`）| `json` |
| `LOG_DIR` | 否 | 日誌檔案目錄（空 = 僅 stdout）| — |
| `LOG_FILE_MAX_BYTES` | 否 | 單檔上限（bytes）| `10485760` |
| `LOG_FILE_BACKUP_COUNT` | 否 | 保留備份數 | `5` |
| `LOG_FILE_PREFIX` | 否 | 日誌檔名前綴（`{prefix}.log`）| `ccas` |
| **帳單 PDF 密碼** | | | |
| `PDF_PASSWORD_<BANK_CODE>` | 是* | 各銀行 PDF 解密密碼 | — |
| **富邦 web-fetch** | | | |
| `FUBON_NATIONAL_ID` | 是* | 身分證字號（富邦網銀登入用）| — |
| `FUBON_ROC_BIRTHDAY` | 是* | 民國年月日 7 碼（例：`0881010`）| — |
| `FUBON_CAPTCHA_MAX_RETRIES` | 否 | OCR + doLogin 迴圈最大重試次數（1-20）| `7` |
| `FUBON_CAPTCHA_FALLBACK_LLM` | 否 | OCR 失敗後是否 fallback 至 Claude Vision | `false` |
| `FUBON_CAPTCHA_ARCHIVE_DIR` | 否 | 成功驗證的 captcha JPEG 存檔目錄（eval 資料集擴充用）| — |
| `FUBON_MANUAL_STAGING_DIR` | 否 | 手動下載 PDF 放置目錄（SPA 自動化失敗時的 fallback）| — |
| **Anthropic（FUBON LLM captcha fallback）** | | | |
| `ANTHROPIC_API_KEY` | 是* | Anthropic API key（僅 `FUBON_CAPTCHA_FALLBACK_LLM=true` 時需要）| — |
| **前端（Vite）** | | | |
| `VITE_API_BASE` | 否 | 後端 API base URL；dev 留空走 Vite proxy，production 或自架後端時才填 | — |
| `VITE_API_PROXY_TARGET` | 否 | Vite dev server 的 `/api` proxy 目標（僅 dev 生效）| `http://127.0.0.1:8000` |

*依實際需求填入；留空時對應功能停用。
<!-- AUTO-GENERATED END -->

### 本地開發啟動（uv + pnpm，無 Docker）

```bash
cp config/banks.example.yaml config/banks.yaml
./scripts/check-env.sh        # 驗證 .env 必填欄位
./scripts/setup.sh            # 一次性：安裝相依、Gmail OAuth、alembic upgrade head、同步 bank config
./scripts/start.sh            # 同時啟動 backend（uvicorn :8000）+ frontend（vite :5173），Ctrl+C 一起收
```

若只想單獨啟動前端：

```bash
cd frontend
pnpm install
pnpm dev                      # http://localhost:5173
```

### Docker Compose（production build）

```bash
docker compose up --build
```

一次啟動 `backend`／`worker`／`scheduler`／`bot`／`frontend`（nginx）／`redis`。backend 容器會透過 `scripts/docker-entrypoint.sh` 自動跑 `check-env` → `alembic upgrade head` → `uvicorn`。

| 對外連接埠 | 服務 |
|---|---|
| `127.0.0.1:8000` | FastAPI |
| `127.0.0.1:8080` | Frontend（nginx） |
| `127.0.0.1:6379` | Redis |

Dev-tools profile（`sqlite-web`、`redis-commander`）需額外加 `--profile dev-tools`。部署細節見 [deployment-guide](docs/deployment-guide.md)。

## 開發指令

### 包裝好的腳本（常用）

```bash
./scripts/dev-lint.sh                      # 後端 ruff check + format --check + pyright
./scripts/dev-test.sh [pytest args]        # 後端 pytest（in-memory SQLite，無 Docker）
./scripts/test.sh [pytest args]            # pytest wrapper，本地與 CI 共用
./scripts/pipeline.sh [pipeline args]      # 在 backend 容器內跑 pipeline CLI
```

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

### Git hooks

**Claude Code 使用者**：無需安裝。Session 結束且有檔案異動時，Stop hook（`.claude/hooks/ccas-pre-push-stop.sh`）自動執行完整品質檢查。

**非 Claude 工作流**（手動 git push）：

```bash
./scripts/setup-hooks.sh       # 安裝 pre-commit + pre-push（需先 `brew install gitleaks`）
```

- `pre-commit`：`gitleaks protect --staged` 掃描 staged diff，偵測秘密即中止 commit
- `pre-push`：後端 `ruff`＋`pyright`＋`pytest --cov ≥ 70%`，前端 `lint`＋`build`＋`test`

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

## 腳本參考

`scripts/` 下共 12 支腳本，全部可從 repo 根目錄呼叫：

| 腳本 | 用途 | 觸發 |
|---|---|---|
| `setup.sh` | 一次性初始化：驗證 `.env`、安裝後端／前端相依、Gmail OAuth、`alembic upgrade head`、同步 `bank-code-registry.yaml` | 手動（首次） |
| `start.sh` | One-click 本地開發：同時啟動 backend（uvicorn :8000）與 frontend（vite :5173），Ctrl+C 一起收 | 手動 |
| `check-env.sh` | 比對 `.env` 與 `.env.example`：空值欄位視為必填，缺少就 `exit 1`；可用 `ENV_FILE=.env.test` 覆寫 | 手動 / CI |
| `dev-lint.sh` | `cd backend && ruff check + ruff format --check + pyright` | 手動 |
| `dev-test.sh` | `cd backend && pytest "$@"`；in-memory SQLite，不需 Docker／tesseract／Redis | 手動 |
| `test.sh` | 與 `dev-test.sh` 等價的 pytest wrapper（CI 亦呼叫同一支） | 手動 / CI |
| `pipeline.sh` | `docker compose exec backend uv run python -m ccas.pipeline "$@"`；在執行中的 backend 容器內跑 pipeline | 手動 |
| `get-telegram-chat-id.sh` | 以 Bot Token 呼叫 `getUpdates` 列出最近聊天室 ID；可帶參數或讀 `.env` 的 `TELEGRAM_BOT_TOKEN` | 手動 |
| `setup-hooks.sh` | 將 `pre-commit.sh` / `pre-push.sh` symlink 到 `.git/hooks/`；非 Claude 工作流使用；偵測 gitleaks 是否安裝並提醒 | 手動（首次，非必要）|
| `pre-commit.sh` | git hook：`gitleaks protect --staged` 掃描 staged diff，偵測秘密即中止 commit | `git commit` |
| `pre-push.sh` | CI 模擬：backend `ruff`＋`pyright`＋`pytest --cov`（門檻 70%），frontend `lint`＋`build`＋`test` | Claude Code Stop hook（自動）/ `git push`（需安裝）|
| `docker-entrypoint.sh` | Backend 容器 entrypoint：驗證環境變數 → 檢查 tesseract → `alembic upgrade head` → `exec uvicorn` | Docker Compose 自動 |

## 文件索引

`docs/` 下共 13 份文件：

**使用與部署**
- [`docs/user-guide.md`](docs/user-guide.md) — 非開發者操作手冊（Docker Compose 啟動、Gmail／Telegram 設定、銀行篩選）
- [`docs/developer-guide.md`](docs/developer-guide.md) — 本地開發環境設定（uv／pnpm、alembic、seed、pipeline CLI）
- [`docs/deployment-guide.md`](docs/deployment-guide.md) — 正式環境部署流程（Docker Compose、OAuth 憑證、Telegram）
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — 營運手冊（健康檢查、RQ worker、log 篩選、migration 回滾、備份）
- [`docs/qa-testing-guide.md`](docs/qa-testing-guide.md) — 獨立部署 QA 測試流程與完整 pipeline 驗證

**貢獻與參考**
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — 分支策略、Conventional Commits、TDD 工作流、80% 覆蓋率要求
- [`docs/bank-codes.md`](docs/bank-codes.md) — 銀行代號對照表（7 支已實作 parser + 不支援清單）
- [`docs/notion.md`](docs/notion.md) — 產品方向 SSOT（願景、roadmap、目前實作狀態）

**CODEMAPS 架構地圖**
- [`docs/CODEMAPS/architecture.md`](docs/CODEMAPS/architecture.md) — 系統總覽、資料流、進入點、技術棧分層
- [`docs/CODEMAPS/backend.md`](docs/CODEMAPS/backend.md) — FastAPI 路由、pipeline 5 階段、模組分層、parser 清單
- [`docs/CODEMAPS/frontend.md`](docs/CODEMAPS/frontend.md) — React 19 + Vite 8 結構、頁面樹、TanStack Query、lazy load
- [`docs/CODEMAPS/data.md`](docs/CODEMAPS/data.md) — SQLite schema、SQLAlchemy models、6 次 migration 歷程
- [`docs/CODEMAPS/dependencies.md`](docs/CODEMAPS/dependencies.md) — 外部整合（Gmail／Telegram／Redis／tesseract／Docker 服務）

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
