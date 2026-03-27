## ADDED Requirements

### Requirement: 初始化 Python 後端專案
系統 SHALL 具備一個由 uv 管理的 Python 3.12+ 後端專案，並在 `backend/` 目錄下提供 `pyproject.toml`，宣告所有必要依賴（`fastapi`、`uvicorn`、`sqlalchemy`、`alembic`、`pydantic-settings`、`pdfplumber`、`pikepdf`、`tabula-py`、`python-telegram-bot`、`google-api-python-client`、`apscheduler`）。

#### Scenario: 後端專案可執行
- **WHEN** 開發者 clone repo 後執行 `cd backend && uv sync`
- **THEN** 所有 Python 依賴都會安裝完成，且 `uv run python -c "import ccas"` 可成功執行

#### Scenario: 後端開發伺服器可啟動
- **WHEN** 開發者執行 `uv run uvicorn ccas.api.app:create_app --factory`
- **THEN** FastAPI 會在 8000 port 啟動，且 `/health` 端點回傳 `{"status": "ok"}`

### Requirement: 初始化 React 前端專案
系統 SHALL 具備一個由 pnpm 管理的 React + TypeScript 前端專案，並在 `frontend/` 目錄中配置 Vite、Tailwind CSS 與 shadcn/ui。

#### Scenario: 前端專案可執行
- **WHEN** 開發者執行 `cd frontend && pnpm install`
- **THEN** 所有 Node 依賴都會安裝完成，且 `pnpm dev` 可在 5173 port 啟動 Vite dev server

#### Scenario: 前端可成功建置
- **WHEN** 開發者執行 `pnpm build`
- **THEN** 建置會成功完成，並在 `frontend/dist/` 產出結果

### Requirement: 目錄結構符合系統規格架構
系統 SHALL 將後端原始碼放在 `backend/src/ccas/` 下，並建立 `ingestor/`、`parser/`、`storage/`、`classifier/`、`bot/`、`api/`、`scheduler/` 子目錄。每個子目錄 SHALL 都包含 `__init__.py`。

#### Scenario: 所有模組目錄都存在
- **WHEN** 專案完成初始化
- **THEN** `backend/src/ccas/` 下會存在全部 7 個模組目錄，且都可作為 Python package import

### Requirement: 提供 Docker Compose 編排
系統 SHALL 在專案根目錄提供 `docker-compose.yaml`，定義兩個服務：`backend`（Python/FastAPI，port 8000）與 `frontend`（Vite dev server，port 5173），並共用名為 `ccas-data` 的 volume 掛載到 backend container 的 `/data`。

#### Scenario: 使用 docker compose 啟動整個系統
- **WHEN** 開發者執行 `docker compose up`
- **THEN** backend 與 frontend 都會成功啟動，且 backend 的 `/health` 端點可在 `http://localhost:8000/health` 存取

#### Scenario: 重啟後資料仍保留
- **WHEN** 先執行 `docker compose down` 再執行 `docker compose up`
- **THEN** `/data/ccas.db` 的 SQLite 資料會保留前一次執行的內容

### Requirement: 提供 backend Dockerfile
後端 Dockerfile SHALL 使用 Python 3.12 base image，安裝 uv，複製 `pyproject.toml` 與 `uv.lock`，安裝依賴後再複製 source code，entrypoint SHALL 執行 uvicorn。

#### Scenario: 後端 Docker image 可成功建置
- **WHEN** 執行 `docker build ./backend`
- **THEN** image 可成功建置，且 `docker run <image> python -c "import ccas"` 可成功執行

### Requirement: 提供 frontend Dockerfile
前端 Dockerfile SHALL 使用 Node 22 base image，安裝 pnpm，複製 `package.json` 與 `pnpm-lock.yaml`，安裝依賴後再複製 source code，entrypoint SHALL 以 `0.0.0.0` 綁定 Vite dev server。

#### Scenario: 前端 Docker image 可成功建置
- **WHEN** 執行 `docker build ./frontend`
- **THEN** image 可成功建置，且 dev server 可以順利啟動
