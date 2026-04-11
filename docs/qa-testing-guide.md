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

編輯 `.env`，填入以下**必要**變數：

```ini
# API 認證（自訂一組安全字串即可）
API_TOKEN=qa-test-token-2026

# Telegram（若不測試通知功能，可填任意值）
TELEGRAM_BOT_TOKEN=placeholder
TELEGRAM_CHAT_ID=0
TELEGRAM_ALLOWED_CHAT_IDS=0

# Gmail 路徑（使用預設值，不影響 API/UI 測試）
GMAIL_CREDENTIALS_PATH=./data/credentials.json
GMAIL_TOKEN_PATH=./data/token.json
STAGING_DIR=./data/staging
```

> 其餘變數皆有合理預設值，無需修改。完整變數說明見 `.env.example`。

### 3. 設定銀行設定檔

```bash
cp config/banks.example.yaml config/banks.yaml
```

### 4. 啟動服務（開發模式含 UI）

```bash
docker compose up --build
```

首次啟動約需 2-3 分鐘（build image + 安裝套件）。啟動後可用的服務：

| 服務 | URL | 說明 |
|------|-----|------|
| Backend API | http://localhost:8000 | REST API |
| API 文件 (Swagger) | http://localhost:8000/docs | 互動式 API 測試 |
| API 文件 (ReDoc) | http://localhost:8000/redoc | API 參考文件 |
| Health Check | http://localhost:8000/health | 健康檢查 |
| Frontend UI | http://localhost:8080 | Web 操作介面（nginx production build） |

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

- **Web UI**：瀏覽器開啟 http://localhost:5173，使用 `.env` 中的 `API_TOKEN` 登入
- **Swagger**：瀏覽器開啟 http://localhost:8000/docs，點擊 Authorize 輸入 token

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
| Analytics | 分類統計 | 依分類顯示消費金額圖表 |
| Analytics | 日趨勢 | 顯示消費時間分布 |
| Analytics | 商家排名 | 按金額排序的商家列表 |
| Settings | 銀行設定 | 顯示 CTBC 設定，可新增/編輯 |
| Settings | 分類管理 | 顯示 46 個關鍵字，可新增/編輯/刪除 |

### B. API 端點測試（透過 Swagger）

所有 API 端點（除 `/health`）需要 Bearer Token 認證。在 Swagger 頁面點擊 **Authorize** 按鈕，輸入 `.env` 中的 `API_TOKEN`。

#### 認證

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/auth/session` | 檢查目前 session 是否已登入 |
| POST | `/api/auth/session` | 登入（body: `{"token": "your-api-token"}`，回傳 204） |
| DELETE | `/api/auth/session` | 登出（回傳 204） |

#### 帳單

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/bills` | 帳單列表（支援 month、year、bank_code、status、page、per_page） |
| PATCH | `/api/bills/{bill_id}` | 更新帳單（標記已繳） |
| GET | `/api/bills/{bill_id}/pdf` | 下載帳單原始 PDF |

#### 交易

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/transactions` | 交易列表（支援 page, per_page） |
| GET | `/api/transactions/export` | 匯出交易明細為 CSV（UTF-8 BOM） |

#### 分析

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/analytics/years` | 可選年度清單 |
| GET | `/api/analytics/trend` | 月消費趨勢（最近 N 個月，預設 6） |
| GET | `/api/analytics/categories` | 分類消費統計（需 `?month=YYYY-MM`） |
| GET | `/api/analytics/banks` | 銀行消費比較（需 `?month=YYYY-MM`） |

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
| 自動化測試 (495 tests) | 可以 | 全部使用 mock，無外部依賴 |

**結論**：無真實憑證的環境可測試約 **80%** 的功能，涵蓋所有 UI、API、CRUD 操作。Pipeline 的 ingest/notify 階段需依賴真實憑證。

---

## 已知限制

1. **僅支援 CTBC（中國信託）**：目前僅實作 CTBC 帳單 parser，其他銀行的 parser 尚未開發
2. **OCR 需 Docker**：tesseract OCR 僅在 Docker production image 中安裝，本機直接執行需手動安裝
3. **Frontend 無覆蓋率工具**：前端測試存在但尚未安裝 `@vitest/coverage-v8`
4. **Bot handlers 無自動化測試**：Telegram bot 的 5 個指令（/status, /upcoming, /summary, /category, /paid）需手動測試
5. **SQLite 單一連線**：不支援多使用者並行寫入，適合單人測試

---

## 環境重置

```bash
# 重置 seed 資料（保留 schema）
docker exec -it ccas-backend-1 uv run python /app/scripts/seed.py --reset

# 完全重建（清除所有容器和資料）
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
2. 確認已執行 seed：檢查 `http://localhost:8000/docs` 中 `/api/bills` 是否有資料

### Seed 失敗

```bash
# 手動套用 migration
docker exec -it ccas-backend-1 uv run alembic upgrade head

# 再次 seed
docker exec -it ccas-backend-1 uv run python /app/scripts/seed.py --reset
```
