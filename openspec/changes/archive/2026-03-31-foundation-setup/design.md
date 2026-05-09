## 背景 (Context)

CCAS 是一個綠地專案，已有定稿的系統規格 [`docs/notion.md`](/home/paul/projects/ccas/docs/notion.md)，但目前尚無任何程式碼。系統整體包含 Python 後端（Gmail ingestor、PDF parser、classifier、Telegram bot、REST API）與 React 前端（dashboard）。本次 `foundation-setup` change 的目的是先建立後續所有功能都會依賴的基礎：專案骨架、資料庫 schema、設定系統與測試基礎建設。

目前狀態只有 OpenSpec 工作流檔案與文件，尚未建立 `backend/` 或 `frontend/` 目錄。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 讓 backend 與 frontend 可以透過 `docker compose up` 啟動
- 透過 Alembic 建立並遷移 4 個資料表
- 後端測試可用 `uv run pytest` 執行，並支援 coverage
- 前端測試可用 `pnpm test` 執行，並支援 coverage
- 支援以 `.env` 為基礎的環境設定管理
- 建立與規格文件模組架構一致且清楚的目錄結構

**非目標：**
- 不實作任何功能本身，不包含 parser、ingestor、bot 或 API route
- 不處理正式環境部署設定，例如 CI/CD 或雲端託管
- 不建立 PDF fixture（seed data 包含在本 change 中，用於開發階段驗證）
- 不建立真正的前端頁面，只保留 health-check placeholder
- 不處理 Telegram 或 Gmail 整合

## 決策 (Decisions)

### D1: 使用 uv 作為 Python 依賴管理工具

**選擇**: uv

**理由**: uv 在依賴解析與安裝速度上遠快於 Poetry，支援原生 lockfile，且在 2025-2026 年有持續成長的生態採用。它是單一 binary，不需要額外的 Python bootstrap。

**考慮過的替代方案**:
- Poetry：成熟，但解析較慢，resolver 較複雜
- pip + requirements.txt：沒有 lockfile，也缺乏標準化的專案 metadata 管理

### D2: 採用含 `backend/` 與 `frontend/` 的 monorepo 結構

**選擇**: 單一 repository，兩個頂層目錄 `backend/` 與 `frontend/`

**理由**: 對單人專案來說最簡單，方便共用 Docker Compose，也容易導航。現階段沒有引入 nx、turborepo 等 monorepo 工具的必要。

**考慮過的替代方案**:
- 拆成多個 repo：對目前規模是額外負擔
- 扁平式結構：Python 與 Node 設定混雜，容易造成混亂

### D3: 使用 SQLAlchemy 2.0 與 Alembic 管理資料庫

**選擇**: SQLAlchemy 2.0 ORM + Alembic migration

**理由**: 可提供型別友善的查詢建構方式，未來也能平滑過渡到 async FastAPI route，並可根據 model 變更產生 migration，是成熟且主流的選擇。

**考慮過的替代方案**:
- 原生 `sqlite3`：缺乏 migration，SQL 容易散落在程式中，也較難測試
- Tortoise ORM：生態較小，成熟度較低
- SQLModel：建立於 SQLAlchemy 之上，但會增加與 Pydantic 的重疊複雜度

### D4: 將 SQLite 放在 Docker volume 中

**選擇**: 使用 named Docker volume，在 `/data/ccas.db` 保存單一 SQLite 檔案

**理由**: 對單人使用工具來說幾乎零設定，適合個人帳單管理工具。named volume 可在 container 重啟後保留資料，也容易備份。

**考慮過的替代方案**:
- PostgreSQL：對單人工具偏重，還要額外維護資料庫服務
- Bind mount：也可行，但 volume 在可攜性上較好

### D5: 使用 pydantic-settings 處理設定

**選擇**: pydantic-settings 搭配 `.env`

**理由**: 啟動時即可做型別驗證，並可自動從環境變數與 `.env` 載入，與 FastAPI 的 Pydantic 生態自然整合。

**考慮過的替代方案**:
- `python-dotenv` + 手動解析：沒有驗證，也缺乏型別安全
- dynaconf：功能比目前需求更多，額外依賴較重

### D6: 前端採用 React + Vite + shadcn/ui

**選擇**: React 19 + Vite + TypeScript + Tailwind CSS + shadcn/ui + Recharts

**理由**: shadcn/ui 提供可直接複製的元件模式，Recharts 與 React 配合自然，Vite 是現代 React 專案的主流建置工具，整體對 dashboard 型產品的生態最成熟。

**考慮過的替代方案**:
- Vue 3 + Naive UI：API 較簡單，但 dashboard 元件生態較小
- Svelte：整體生態較小，圖表選項較少
- Next.js：目前不需要 SSR，屬於過度配置

### D7: 使用 2 個服務的 Docker Compose

**選擇**: `backend`（Python/FastAPI）與 `frontend`（Node/Vite dev server）兩個 container，共用 SQLite volume

**理由**: 可以提供一致的開發環境，也較貼近未來部署型態。前端透過 Docker 網路代理 API 到 backend。

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: ["ccas-data:/data"]
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
volumes:
  ccas-data:
```

## 風險 / 取捨 (Risks / Trade-offs)

**SQLite 並行能力有限** -- SQLite 在多寫入情境下有並行限制。對單人工具與單一 scheduler process 來說可接受；若未來有多使用者需求，再轉向 PostgreSQL。  
- 緩解方式：啟用 WAL mode（`PRAGMA journal_mode=WAL`）提升讀取並行性。

**uv 生態仍較新** -- uv 相較 Poetry 較新，複雜依賴樹可能遇到少量邊界問題。  
- 緩解方式：uv 有活躍維護與強背書，必要時仍可退回 pip。

**SQLite 存在 Docker volume 中** -- volume 綁定主機，若 volume 遺失就會失去資料。  
- 緩解方式：後續補上備份流程文件，或加入定期備份機制。

**前端 dev server 跑在 Docker 中** -- HMR 可能比原生環境慢。  
- 緩解方式：需要時可調整 Vite `server.watch.usePolling`，開發者也可選擇直接在本機執行 `pnpm dev`。

## 未決問題 (Open Questions)

- Alembic 初期要使用 async engine 還是 sync engine？  
  目前決定：先使用 sync，未來有 async route 再調整。
- 是否要提交含 placeholder 的 `.env.example`？  
  目前決定：要，作為設定文件的一部分。
