# CCAS — 信用卡帳單自動化系統

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/hmj1026/ccas?label=release&color=blue)](https://github.com/hmj1026/ccas/releases/latest)

[English](README.md) | **繁體中文**

> 一條把台灣銀行信用卡 e-statement 變成可搜尋、自動分類儀表板的端到端流水線 —— 不用再手動記帳。

CCAS 從 Gmail 拉取加密 PDF 帳單，用各銀行密碼解密，逐筆解析交易、分類消費類別，最終透過 REST API、React 儀表板與 Telegram Bot 呈現。設計上跑在你自己的機器、用 Docker Compose 啟動 —— 你的財務資料不會離開本機。

## 功能

- **多銀行 PDF 解析** —— CTBC、E.SUN、Taishin、UBOT、Cathay、SinoPac、Fubon（7 個 parser，registry 模式可擴充）
- **Gmail OAuth 自動收信** —— 排程抓取帳單附件，staging idempotent
- **個人分類規則** —— keyword / exact / regex 三種 pattern + priority，含 100ms regex fail-soft timeout
- **手動覆寫** —— 在 `/transactions/{id}` 改類別、標籤、商家別名；pipeline 不會覆蓋手動編輯
- **預算與提醒** —— 每月總額 / 單類別 / 單銀行三 scope，80% 與 100% Telegram 推播；逐張帳單付款提醒
- **Insights** —— 月趨勢、銀行對比、年度對比、商家排行、類別 vs 上月
- **匯出** —— 串流 CSV / XLSX，支援日期 / 銀行 / 類別 filter
- **預設即安全** —— HMAC 簽章 session cookie、登入端點速率限制（僅計 POST）、日誌機敏值自動遮罩、生產環境預設關閉 OpenAPI docs

## 系統架構

```
Gmail ─► staged PDF ─► decrypted PDF ─► Bill + Transaction[] ─► categorized Transaction
                                                │                         │
                                                ▼                         ▼
                                           REST API ──────────► React Dashboard
                                                │
                                                ▼
                                          Telegram Bot  ◄── payment reminders
```

Pipeline 各階段以狀態機推進：`staged → decrypted → parsed`，遇到 `decrypt_failed` / `parse_failed` 走重試路徑，3 次後升級為 `manual_review_needed`。

## 技術棧

| 層級 | 技術 |
|---|---|
| **後端** | Python 3.12、FastAPI、SQLAlchemy (async) + aiosqlite、Alembic、RQ + Redis、APScheduler |
| **前端** | React 19、Vite 8、TypeScript 5.9、Tailwind CSS 4、TanStack Query 5、React Router 7、Recharts |
| **PDF / OCR** | pdfplumber、pikepdf、tabula-py、pytesseract、ddddocr（富邦 captcha） |
| **測試** | pytest（asyncio_mode=auto、cov ≥ 70%）、Vitest、Playwright |
| **Lint / Type** | ruff（check + format）、pyright、eslint |
| **基礎設施** | Docker Compose、SQLite（WAL + busy_timeout）、Nginx proxy |
| **套件管理** | uv（後端）、pnpm（前端） |

## 快速開始（Docker）

需要 Docker + Docker Compose。首次安裝前請先依 [`docs/gmail-setup.md`](docs/gmail-setup.md) 建立 Google Cloud OAuth client。

```bash
mkdir ~/ccas && cd ~/ccas
RELEASE=v0.3.0   # 改為要安裝的精確版號
curl -fsSL -o docker-compose.yml \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/docker-compose.yml"
curl -fsSL -o example.env \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/example.env"
cp example.env .env
# 必填：REPO_OWNER、CCAS_VERSION、CCAS_PORT、PUBLIC_BASE_URL
# 選填（可稍後在 /setup/secrets 設定）：Telegram、PDF 密碼
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

啟動後：

1. 取得自動產生的登入 token：`cat ./data/secrets/api-token`
2. 開 `http://localhost:8080/login`，貼上 token
3. 進「設定中心」上傳 Gmail `credentials.json`、啟用銀行、設定 PDF 密碼

完整步驟（含 env 變數逐項說明）：[`docs/install-quickstart.md`](docs/install-quickstart.md)。

## 本地開發

不使用 Docker —— 需要 Python 3.12+、Node.js 22+、`uv`、`pnpm`。

```bash
cp .env.example .env
cp config/banks.example.yaml config/banks.yaml
./scripts/setup.sh        # 一次性：安裝相依、Gmail OAuth、alembic upgrade head
./scripts/start.sh        # 同時啟動 backend（:8000）+ frontend（:5173），Ctrl+C 一起收
./scripts/dev-test.sh     # 後端 pytest（in-memory SQLite）
./scripts/dev-lint.sh     # ruff + pyright
```

只跑前端：

```bash
cd frontend && pnpm install && pnpm dev    # http://localhost:5173
pnpm test           # Vitest
pnpm e2e            # Playwright
```

完整工具鏈說明見 [`docs/developer-guide.md`](docs/developer-guide.md)。

## 專案結構

```
ccas/
├── backend/           # FastAPI 服務（src/ccas/{api,ingestor,decryptor,parser,
│                      #   classifier,pipeline,scheduler,bot,storage,tools}）
├── frontend/          # React 19 + Vite 8 + TypeScript
├── docker/            # 正式環境 pull-only compose + nginx proxy image
├── docker-compose.yaml          # dev compose（從原始碼 build）
├── docker-compose.override.yml  # dev 覆寫（bind-mount、hot reload）
├── config/            # banks.yaml、categories.yaml、bank-code-registry.yaml
├── scripts/           # 16 支 shell script：setup、start、lint、test、hooks…
├── docs/              # user / developer / deployment / RUNBOOK + CODEMAPS/
├── openspec/          # spec-driven change workflow artifacts
└── .env.example       # 環境變數範本（SSOT）
```

## 文件索引

| 主題 | 檔案 |
|---|---|
| 安裝（非開發者） | [`docs/install-quickstart.md`](docs/install-quickstart.md) |
| 使用者操作手冊 | [`docs/user-guide.md`](docs/user-guide.md) |
| 開發者指南 | [`docs/developer-guide.md`](docs/developer-guide.md) |
| 正式環境部署 | [`docs/deployment-guide.md`](docs/deployment-guide.md) |
| 維運 Runbook | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) |
| 個人規則與預算 | [`docs/personal-rules-and-budgets.md`](docs/personal-rules-and-budgets.md) |
| Gmail OAuth 設定 | [`docs/gmail-setup.md`](docs/gmail-setup.md) |
| 銀行代碼對照 | [`docs/bank-codes.md`](docs/bank-codes.md) |
| 貢獻指南 | [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) |

架構地圖（給貢獻者）：[`docs/CODEMAPS/`](docs/CODEMAPS/) —— `architecture.md`、`backend.md`、`frontend.md`、`data.md`、`dependencies.md`。

## CI/CD

GitHub Actions 於 push 與 PR 至 `develop` / `master` 時觸發：

- **backend-lint** —— `ruff check` + `ruff format --check` + `pyright`
- **backend-test** —— `pytest tests/unit/`，覆蓋率 ≥ 70%
- **frontend-lint-test** —— `pnpm lint` + `pnpm build`（含 `tsc`） + `pnpm test`

發佈流程（`release-docker.yaml`）在打 tag 時 build & push 容器 image 到 GHCR。

## 貢獻

分支策略、Conventional Commits、TDD 工作流、80% 覆蓋率政策見 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)。

## 授權

採用 [MIT License](LICENSE) —— © 2026 Paul。你可以自由使用、修改、散佈本軟體，唯需保留版權聲明與授權條款全文。
