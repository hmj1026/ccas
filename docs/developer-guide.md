# CCAS 開發者指南

本指南面向開發者，涵蓋環境設定、架構總覽、測試和貢獻流程。

## 前置需求

- Docker Engine 24+ 和 Docker Compose v2（推薦）
- Python 3.12+、[uv](https://docs.astral.sh/uv/)（本地開發用）
- Node.js 22+ 和 pnpm（前端開發用；CI 與 Dockerfile 使用 Node 22）
- Git

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

本機開發時，路徑變數預設使用 `./data/`，實際會解析到 `backend/data/`。
Docker Compose 啟動時會再覆寫成容器內的 `/data/` 掛載點。

驗證環境變數：
```bash
./scripts/check-env.sh
```

## 3. 初始化

首次設定執行：
```bash
./scripts/setup.sh
```

此腳本會：驗證環境變數 -> 安裝依賴 -> Gmail OAuth 認證 -> 資料庫 migration -> 同步銀行設定。

## 4. 啟動開發伺服器（Docker，推薦）

```bash
docker compose up --build
```

Docker Compose 以開發模式啟動：
- **Backend**: uvicorn with `--reload`、tesseract OCR 已內建
- **Frontend**: Vite dev server（port 5173，hot reload）
- **Redis**: 本地容器

Dev 模式將 `backend/data/` 掛載到容器的 `/data/`，原始碼變更即時生效。

### 服務位址

| 服務 | 位址 |
|------|------|
| Backend API | http://127.0.0.1:8000 |
| Frontend | http://localhost:5173 |
| API Docs | http://127.0.0.1:8000/docs |

> Frontend port `5173` 為 `./scripts/start.sh`（本機 uv + pnpm）使用的 Vite dev server；若改用 Docker Compose，frontend 服務走 nginx production build，對外為 `http://localhost:8080`（見 `docker-compose.yaml`）。

### 開發者 GUI 工具（資料檢視）

啟動資料庫與快取的瀏覽器 GUI（opt-in）：

```bash
docker compose --profile dev-tools up
```

| 工具 | 用途 | 位址 |
|------|------|------|
| sqlite-web | SQLite 資料表瀏覽、SQL 查詢 | http://localhost:8088 |
| redis-commander | Redis keys 瀏覽、值檢視 | http://localhost:8081 |

**注意事項：**
- sqlite-web 以 read-only 模式掛載，無法透過 GUI 修改資料
- redis-commander 自動連線至 Redis，啟動即用
- 這些服務僅在指定 `--profile dev-tools` 時啟動，不影響預設流程
- redis-commander 中 RQ job data 顯示為亂碼屬正常現象（RQ 使用 pickle + zlib 序列化）。檢視 job 資訊請用 CLI：
  ```bash
  docker compose exec worker uv run rq info --url redis://redis:6379/0
  docker compose exec worker uv run rq job <job-id> --url redis://redis:6379/0
  ```

**Port 衝突排解：** 若 8088 或 8081 已被佔用，可在 `docker-compose.yaml` 中修改對應的 host port mapping（冒號左側的數字）。

**本地開發替代方案（不使用 Docker 時）：**
- **SQLite**: VS Code 安裝 [SQLite Viewer](https://marketplace.visualstudio.com/items?itemName=qwtel.sqlite-viewer) 擴充功能，直接開啟 `backend/data/ccas.db`
- **SQLite CLI**: `sqlite3 backend/data/ccas.db`（macOS 內建）
- **Redis**: `redis-cli`（需本地安裝 Redis）

### Docker 內執行 Pipeline

```bash
# 透過便利腳本（推薦）
./scripts/pipeline.sh --bank CTBC
./scripts/pipeline.sh --from parse --to classify --force

# 或直接 docker compose exec
docker compose exec backend uv run python -m ccas.pipeline --bank CTBC
```

### Docker 內執行測試

```bash
# 透過便利腳本（推薦）
./scripts/test.sh
./scripts/test.sh tests/unit/ -v
./scripts/test.sh --cov --cov-report=term-missing

# 或直接 docker compose exec
docker compose exec backend uv run pytest
```

### Production 模式（僅 base compose）

```bash
docker compose -f docker-compose.yaml up --build
```

此指令不合併 override，僅啟動 backend、scheduler、bot、redis（不含 frontend）。
Frontend 僅供開發驗證資料，production 透過 Telegram bot 存取。
詳見 [部署指南](deployment-guide.md)。

## 5. 本地開發（進階，無 Docker）

不使用 Docker 時，部分功能受限：
- tesseract OCR 需手動安裝（`apt-get install tesseract-ocr tesseract-ocr-chi-tra`）
- 未安裝 tesseract 時 merchant OCR 會略過（graceful fallback）

### 腳本啟動

```bash
./scripts/start.sh
```

### 分別啟動

```bash
# Terminal 1: Backend
cd backend && uv run uvicorn ccas.api.app:create_app --factory --reload

# Terminal 2: Frontend
cd frontend && pnpm dev
```

## 6. 架構總覽

### 技術棧

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| Database | SQLite (WAL mode) |
| Frontend | React, Vite, TypeScript, Tailwind CSS |
| OCR | tesseract-ocr + chi-tra（Docker 內建） |
| Integrations | Gmail API, Telegram Bot |

### Pipeline 五階段

```
Gmail Inbox
    |
[INGEST]   -> StagedAttachment (從 Gmail 下載 PDF；FUBON 另含 web-fetch + captcha 解析)
    |
[DECRYPT]  -> 解密 PDF (pikepdf + bank-specific password)
    |
[PARSE]    -> Bill + Transaction (pdfplumber + tesseract OCR 提取資料)
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
  ingestor/     # Gmail 附件下載 + staging；`fetcher/` 子模組含 BaseFetcher 介面、FUBON web-fetch 流程、captcha OCR（ddddocr）與 Claude Vision LLM fallback
  parser/       # PDF parsing (per-bank)
  pipeline/     # Orchestration + CLI
  scheduler/    # APScheduler jobs
  storage/      # SQLAlchemy models + database
```

## 7. 測試

### 從專案根目錄執行（推薦）

測試使用 in-memory SQLite，不需 Docker、tesseract 或 Redis。

```bash
./scripts/dev-test.sh                      # 全部測試
./scripts/dev-test.sh tests/unit/ -v       # 只跑 unit tests
./scripts/dev-test.sh tests/integration/   # 只跑 integration tests
./scripts/dev-test.sh --cov --cov-report=term-missing  # 含 coverage
./scripts/dev-test.sh -x                   # 第一個失敗就停
```

### 從 backend/ 目錄執行

```bash
cd backend
uv run pytest
uv run pytest tests/unit/
```

### Docker 環境（QA 或需 OCR 時）

需先啟動容器（`docker compose up --build`）：

```bash
./scripts/test.sh                          # 全部測試（含 tesseract OCR）
./scripts/test.sh tests/unit/ -v           # 只跑 unit tests
```

## 8. 程式碼品質

### 從專案根目錄（推薦）

```bash
./scripts/dev-lint.sh                      # ruff check + format check + pyright
```

### 從 backend/ 目錄

```bash
cd backend
uv run ruff check .
uv run ruff format .
uv run pyright
```

## 9. 資料庫 Migration

```bash
cd backend

# 套用所有 migration
uv run alembic upgrade head

# 建立新 migration
uv run alembic revision --autogenerate -m "description"
```

## 10. Seed Data

```bash
cd backend

# 新增測試資料
uv run python scripts/seed.py

# 清除後重建
uv run python scripts/seed.py --reset
```

## 11. Pipeline CLI

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

## 12. 貢獻指南

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
