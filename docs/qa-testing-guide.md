# CCAS QA 測試指南

本指南面向 QA 測試人員，說明如何在異地環境獨立部署 CCAS 並進行功能測試。

## 前置需求

- Docker Engine 24+ 和 Docker Compose v2
- Git（clone 專案用）
- 至少 2GB RAM（tesseract OCR 需要記憶體）

### 可選（完整 pipeline 測試才需要）

- Google Cloud 專案（啟用 Gmail API，OAuth 憑證）
- Telegram Bot token 和 Chat ID
- 真實的 CTBC 信用卡帳單 PDF

## 快速上手

### 1. 取得專案

```bash
git clone <repository-url>
cd ccas
git checkout develop    # 或指定的測試分支
```

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`。Docker entrypoint 會在 `API_TOKEN` 未設定時自動產生 token；若要固定測試憑證可自行填入。Gmail、Telegram 與銀行密碼只在測試對應功能時需要：

```ini
# 可選：固定 API 認證；不填則從 data/secrets/api-token 讀取 entrypoint 產生的 token
API_TOKEN=qa-test-token-2026
API_COOKIE_SECURE=false

# 路徑預設值（不測試 Gmail/pipeline 時不需準備檔案）
GMAIL_CREDENTIALS_PATH=./data/credentials.json
GMAIL_TOKEN_PATH=./data/token.json
STAGING_DIR=./data/staging
```

> 其餘變數皆有合理預設值，無需修改。完整變數說明見 `.env.example`。

### 3. 設定銀行設定檔

```bash
cp config/banks.example.yaml config/banks.yaml
```

### 4. 啟動服務（根目錄 Compose 開發模式含 UI）

```bash
docker compose up --build
```

首次啟動約需 2-3 分鐘（build image + 安裝套件）。啟動後可用的服務：

| 服務 | URL | 說明 |
|------|-----|------|
| Backend API | http://localhost:8000 | REST API |
| API 文件 (Swagger) | http://localhost:8000/docs | 先在 `.env` 設 `ENABLE_API_DOCS=true` 才啟用 |
| API 文件 (ReDoc) | http://localhost:8000/redoc | 同上；預設關閉 |
| Health Check | http://localhost:8000/health | 健康檢查 |
| Frontend UI | http://localhost:5173 | Vite 開發伺服器（override 自動載入） |

### 5. 寫入測試資料

開啟新 terminal：

```bash
docker exec -it ccas-backend-1 uv run python /app/scripts/seed.py --reset
```

此命令會寫入：
- 1 個銀行設定（CTBC 中國信託）
- 46 個消費分類關鍵字（日用品、超商、餐飲、交通等）
- 1 張帳單（2026 年 3 月，總額 28,500 元）
- 5 筆交易明細（含國內消費、外幣消費、分期付款）

### 6. 開始測試

- **Web UI**：瀏覽器開啟 http://localhost:5173；使用固定的 `.env` token，或 `cat data/secrets/api-token` 取得自動產生的 token
- **Swagger**：只有 `ENABLE_API_DOCS=true` 時可開啟 http://localhost:8000/docs，再點擊 Authorize 輸入 Bearer token

---

## 測試範圍

### A. Web UI 功能測試

| 頁面 | 測試項目 | 預期結果 |
|------|---------|---------|
| 登入 | 輸入正確/錯誤 token | 正確：進入 Dashboard；錯誤：顯示錯誤訊息 |
| Overview | 載入 Dashboard | 顯示帳單摘要、總金額 |
| Bills | 帳單列表 | 顯示 seed 的 1 張帳單 |
| Bills | 標記已繳 | 切換 is_paid 狀態 |
| Transactions | 交易列表 | 顯示 5 筆交易、支援分頁 |
| Transactions | CSV 匯出 | 點擊匯出按鈕下載 CSV 檔案 |
| Insights | 分類統計 | 依分類顯示消費金額圖表 |
| Insights | 月趨勢 | 顯示消費時間分布 |
| Insights | 商家排名 | 按金額排序的商家列表 |
| Settings | 銀行設定 | 顯示 CTBC 設定，可新增/編輯 |
| Settings | 分類管理 | 顯示 46 個關鍵字，可新增/編輯/刪除 |

### B. API 端點測試（透過 Swagger）

健康端點與 `GET/POST /api/auth/session` 不需 Bearer；其餘業務端點需要 Bearer Token。在啟用 OpenAPI 後，於 Swagger 點擊 **Authorize**，輸入固定的 `.env` token，或 entrypoint 產生的 token。

#### 認證

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/auth/session` | 檢查目前 session 是否已登入 |
| POST | `/api/auth/session` | 登入（body: `{"token": "your-api-token"}`，回傳 204） |
| DELETE | `/api/auth/session` | 登出（回傳 204） |

#### 帳單

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/bills` | 帳單列表（支援 month、year、bank_code、status、page、page_size） |
| PATCH | `/api/bills/{bill_id}` | 更新帳單（標記已繳） |
| GET | `/api/bills/{bill_id}/pdf` | 下載帳單原始 PDF |

#### 交易

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/transactions` | 交易列表（支援 month、year、bank_code、category、q、sort、page、page_size） |
| GET | `/api/transactions/export` | 匯出交易明細為 CSV 或 xlsx，可用日期、銀行、分類篩選 |

#### 分析

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/analytics/years` | 可選年度清單 |
| GET | `/api/analytics/trend` | 月消費趨勢（最近 N 個月，預設 6） |
| GET | `/api/analytics/categories` | 分類消費統計（需 `?month=YYYY-MM`） |
| GET | `/api/analytics/categories/compare` | 類別月對月比較（`month` 必填） |
| GET | `/api/analytics/banks` | 銀行消費比較（需 `?month=YYYY-MM`） |
| GET | `/api/analytics/compare/banks` | Insights 銀行比較 |
| GET | `/api/analytics/compare/years` | Insights 年度比較 |
| GET | `/api/analytics/top-merchants` | Insights 商家排行 |

#### 設定

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/settings/banks` | 銀行設定列表 |
| POST | `/api/settings/banks` | 新增銀行設定 |
| PATCH | `/api/settings/banks/{bank_id}` | 更新銀行設定 |
| GET | `/api/settings/categories` | 分類列表 |
| POST | `/api/settings/categories` | 新增分類關鍵字 |
| PATCH | `/api/settings/categories/{id}` | 更新分類 |
| DELETE | `/api/settings/categories/{id}` | 刪除分類 |

#### 概覽 / Pipeline

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/overview` | Dashboard 摘要 |
| POST | `/api/pipeline/trigger` | 觸發 pipeline 執行（需 Redis） |
| GET | `/api/pipeline/status` | Pipeline 狀態摘要 |

### C. Pipeline 功能測試（需真實憑證）

> 此部分需要真實的 Gmail OAuth 憑證和 Telegram Bot token。若無法取得，可跳過。

```bash
# 完整 pipeline
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC

# 指定月份
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --year 2026 --month 3

# 強制重新處理
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --force --bank CTBC

# 只執行特定階段
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --from parse --to classify
```

Pipeline 階段順序：`ingest` -> `decrypt` -> `parse` -> `classify` -> `notify`

### D. 自動化測試

> 自動化測試需在**本機**執行（production container 不含 `tests/` 目錄與開發套件）。  
> 前置需求：本機安裝 Python 3.12+ 與 uv。

```bash
# 執行全部自動化測試（本機）
./scripts/test.sh -q

# 只跑 unit 測試（較快）
./scripts/test.sh tests/unit/ -q

# 跑 E2E 測試
./scripts/test.sh tests/e2e/ -q

# 含覆蓋率報告
./scripts/test.sh --cov --cov-report=term-missing
```

---

## 無真實憑證的測試策略

若 QA 環境無法取得 Gmail/Telegram 憑證：

| 功能 | 可否測試 | 方式 |
|------|---------|------|
| Web UI 所有頁面 | 可以 | 使用 seed data |
| API CRUD 操作 | 可以 | 透過 Swagger |
| 帳單/交易/分析/設定 | 可以 | seed data 已含完整範例 |
| Pipeline (ingest) | 不可 | 需真實 Gmail 憑證 |
| Pipeline (parse/classify) | 部分 | 自動化測試已覆蓋 |
| Telegram 通知 | 不可 | 需真實 Bot token |
| 自動化測試 (1000+ tests) | 可以 | 全部使用 mock，無外部依賴 |

**結論**：無真實憑證的環境可測試約 **80%** 的功能，涵蓋所有 UI、API、CRUD 操作。Pipeline 的 ingest/notify 階段需依賴真實憑證。

---

## 已知限制

1. **支援 7 家銀行**：CTBC（中國信託）、SINOPAC（永豐）、ESUN（玉山）、UBOT（聯邦）、CATHAY（國泰）、TAISHIN（台新）、FUBON（台北富邦）皆已實作完整 parser
2. **OCR 需 Docker**：tesseract OCR 僅在 Docker production image 中安裝，本機直接執行需手動安裝
3. **Frontend coverage**：已安裝 `@vitest/coverage-v8`，可在 `frontend/` 執行 `pnpm test:coverage`；CI 也會執行 coverage。
4. **SQLite 併發邊界**：資料庫是單一檔案，已啟用 WAL 與 30 秒 busy timeout 以支援 backend、worker、scheduler 的程序間協作；仍不定位為高併發多使用者資料庫。

---

## 環境重置

```bash
# 重置 seed 資料（保留 schema）
docker exec -it ccas-backend-1 uv run python /app/scripts/seed.py --reset

# 移除容器與 named volumes；根目錄 Compose 的 backend/data 是 bind mount，不會被此命令刪除
docker compose down -v
docker compose up --build
```

---

## 故障排除

### 服務啟動失敗

```bash
# 檢查環境變數
./scripts/check-env.sh

# 查看 logs
docker compose logs backend
docker compose logs redis
```

### API 回傳 401

確認 `.env` 中的 `API_TOKEN` 與登入時使用的 token 一致。

### 前端無法載入資料

1. 確認 backend 正常：`curl http://localhost:8000/health`
2. 確認已執行 seed：若已設 `ENABLE_API_DOCS=true`，檢查 `http://localhost:8000/docs` 的 `/api/bills`；否則使用受保護 API 並帶 Bearer token

### Seed 失敗

```bash
# 手動套用 migration
docker exec -it ccas-backend-1 uv run alembic upgrade head

# 再次 seed
docker exec -it ccas-backend-1 uv run python /app/scripts/seed.py --reset
```
