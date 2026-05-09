## 緣由 (Why)

CCAS 已經有完整的系統規格文件 [`docs/notion.md`](/home/paul/projects/ccas/docs/notion.md)，但目前還沒有任何可執行程式碼。在開始實作 parser、ingestor、bot、dashboard 之前，專案需要先具備可運作的基礎設施：Python 後端骨架、React 前端骨架、資料庫 schema、Docker 編排與測試基礎建設。沒有這一層地基，後續功能無法穩定展開。

## 變更內容 (What Changes)

- 使用 uv、FastAPI、SQLAlchemy 與 pytest 初始化 Python 3.12+ 後端專案
- 使用 pnpm、React、Vite、TypeScript、Tailwind、shadcn/ui 與 vitest 初始化前端專案
- 建立 4 個核心資料表 `bills`、`transactions`、`categories`、`bank_configs` 的 SQLAlchemy ORM model 與 Alembic migration
- 設定 Docker Compose，協調 backend + frontend，並共用 SQLite volume
- 使用 pydantic-settings 建立基於環境變數與 `.env` 的設定管理
- 建立測試基礎建設：後端 pytest、前端 vitest、coverage 設定
- 建立與系統規格架構一致的專案目錄結構

## 能力範圍 (Capabilities)

### 新增能力 (New Capabilities)

- `project-scaffold`: Python 後端與 React 前端初始化、目錄結構、依賴管理（uv、pnpm）與 Docker Compose 編排
- `database-schema`: `bills`、`transactions`、`categories`、`bank_configs` 的 SQLAlchemy ORM model 與 Alembic migration 支援
- `app-config`: 透過 pydantic-settings、`.env` 與環境變數的集中式設定管理
- `test-infrastructure`: pytest 與 vitest 設定、coverage 報告、fixture 模式與測試目錄慣例

### 修改能力 (Modified Capabilities)

(無 -- 這是綠地專案)

## 影響範圍 (Impact)

- **新增檔案**: 約 30 個檔案，分布於 `backend/`、`frontend/` 與 `docker-compose.yaml`
- **依賴套件**: Python 套件（`fastapi`、`sqlalchemy`、`alembic`、`pydantic-settings`、`pytest`、`pytest-cov`），Node 套件（`react`、`vite`、`tailwindcss`、`shadcn/ui`、`vitest`）
- **基礎設施**: 2 個服務的 Docker Compose（backend、frontend）與 SQLite 共用 volume
- **開發流程**: 後端使用 `uv run pytest`，前端使用 `pnpm test`，整體啟動使用 `docker compose up`
