# CCAS 開發者指南

本指南面向開發者，涵蓋環境設定、架構總覽、測試和貢獻流程。

## 前置需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python 套件管理)
- Node.js 18+ 和 pnpm
- Git
- Redis（可選，排程用）

## 1. 取得專案

```bash
git clone <repository-url>
cd ccas
```

## 2. 環境設定

```bash
cp .env.example .env
cp config/banks.example.yaml config/banks.yaml
```

編輯 `.env`，填入必要變數（詳見 [使用者操作手冊](user-guide.md#2-設定環境變數)）。

驗證環境變數：
```bash
./scripts/check-env.sh
```

## 3. 初始化

首次設定執行：
```bash
./scripts/setup.sh
```

此腳本會：驗證環境變數 → 安裝依賴 → Gmail OAuth 認證 → 資料庫 migration → 同步銀行設定。

## 4. 啟動開發伺服器

一鍵啟動 backend + frontend：
```bash
./scripts/start.sh
```

或分別啟動：
```bash
# Terminal 1: Backend
cd backend && uv run uvicorn ccas.api.app:create_app --factory --reload

# Terminal 2: Frontend
cd frontend && pnpm dev
```

服務位址：
- Backend: http://127.0.0.1:8000
- Frontend: http://localhost:5173
- API docs: http://127.0.0.1:8000/docs

## 5. 架構總覽

### 技術棧

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | SQLite (WAL mode) |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| Integrations | Gmail API, Telegram Bot |

### Pipeline 五階段

```
Gmail Inbox
    |
[INGEST]   -> StagedAttachment (從 Gmail 下載 PDF)
    |
[DECRYPT]  -> 解密 PDF (pikepdf + bank-specific password)
    |
[PARSE]    -> Bill + Transaction (pdfplumber 提取資料)
    |
[CLASSIFY] -> Transaction.category (關鍵字分類)
    |
[NOTIFY]   -> Telegram 通知 (帳單摘要)
```

### 目錄結構

```
backend/src/ccas/
  api/          # FastAPI routers
  bot/          # Telegram bot handler
  classifier/   # Keyword-based classification
  config.py     # Pydantic settings
  decryptor/    # PDF decryption
  ingestor/     # Gmail attachment download
  parser/       # PDF parsing (per-bank)
  pipeline/     # Orchestration + CLI
  scheduler/    # APScheduler jobs
  storage/      # SQLAlchemy models + database
```

## 6. 測試

```bash
cd backend

# 全部測試
uv run pytest

# 含 coverage
uv run pytest --cov --cov-report=term-missing

# 只跑 unit tests
uv run pytest tests/unit/

# 只跑 integration tests
uv run pytest tests/integration/

# 第一個失敗就停
uv run pytest -x
```

## 7. 程式碼品質

```bash
cd backend

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run pyright
```

## 8. 資料庫 Migration

```bash
cd backend

# 套用所有 migration
uv run alembic upgrade head

# 建立新 migration
uv run alembic revision --autogenerate -m "description"
```

## 9. Seed Data

```bash
# 新增測試資料
uv run python scripts/seed.py

# 清除後重建
uv run python scripts/seed.py --reset
```

## 10. Pipeline CLI

```bash
cd backend

# 完整執行
uv run python -m ccas.pipeline

# 指定銀行和月份
uv run python -m ccas.pipeline --bank CTBC --year 2026 --month 3

# 強制重新處理
uv run python -m ccas.pipeline --force

# 指定階段範圍
uv run python -m ccas.pipeline --from parse --to classify
```

## 11. 貢獻指南

### Branching

- `master`: 穩定版本
- `develop`: 開發分支
- Feature branches: `feat/<name>`
- Bug fix branches: `fix/<name>`

### Commit Messages

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```
feat: add CTBC parser ROC format support
fix: correct date parsing for December billing
refactor: extract pipeline stage validation
docs: update developer guide
test: add stage control unit tests
```

### PR 流程

1. 從 `develop` 建立 feature branch
2. 實作 + 測試（80% coverage）
3. `uv run ruff check . && uv run ruff format . && uv run pyright`
4. 推送並建立 PR 到 `develop`
