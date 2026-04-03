# CCAS 使用者操作手冊

本手冊面向非開發者使用者，涵蓋從環境設定到日常操作的完整流程。

## 前置需求

- Docker 和 Docker Compose（[安裝指南](https://docs.docker.com/get-docker/)）
- Google Cloud 專案（啟用 Gmail API，下載 OAuth 憑證）
- Telegram Bot（透過 BotFather 建立）

## 1. 取得專案

```bash
git clone <repository-url>
cd ccas
```

## 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入以下必要變數：

| 變數 | 說明 | 範例 |
|------|------|------|
| `API_TOKEN` | API 認證 token（自訂一組安全字串） | `my-secret-token-2026` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token（從 BotFather 取得） | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | Telegram 聊天室 ID | `123456789` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 允許的聊天室 ID（可同 CHAT_ID） | `123456789` |
| `GMAIL_CREDENTIALS_PATH` | Google OAuth 憑證路徑 | `./data/credentials.json` |
| `GMAIL_TOKEN_PATH` | Gmail token 儲存路徑 | `./data/token.json` |
| `STAGING_DIR` | PDF 暫存目錄 | `./data/staging` |

本機直接執行腳本時，以上 `./data/...` 會解析到 `backend/data/...`。
若用 Docker Compose 啟動，容器內會覆寫成 `/data/...` 掛載點。

### 可選環境變數

以下變數皆有預設值，可依需求覆寫：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ccas.db` | 資料庫連線字串 |
| `API_HOST` | `0.0.0.0` | API 伺服器綁定位址 |
| `API_PORT` | `8000` | API 伺服器連接埠 |
| `FRONTEND_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | CORS 允許來源 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 連線字串 |
| `LOG_LEVEL` | `INFO` | 日誌等級（DEBUG / INFO / WARNING / ERROR） |
| `LOG_FORMAT` | `json` | 日誌格式（json / text） |
| `API_SESSION_COOKIE_NAME` | `ccas_session` | 瀏覽器 session cookie 名稱 |
| `API_SESSION_MAX_AGE` | `43200`（12 小時） | Session 有效時間（秒） |
| `API_COOKIE_SECURE` | `False` | 是否僅透過 HTTPS 傳送 cookie |

## 3. 設定 Gmail API

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立專案 → 啟用 Gmail API
3. 建立 OAuth 2.0 用戶端 ID（桌面應用程式）
4. 下載 `credentials.json`，放到 `.env` 中 `GMAIL_CREDENTIALS_PATH` 指定的路徑

## 4. 設定 Telegram Bot

1. 在 Telegram 搜尋 `@BotFather`
2. 輸入 `/newbot`，依指示建立 bot
3. 記下 bot token，填入 `.env` 的 `TELEGRAM_BOT_TOKEN`
4. 對 bot 傳送任意訊息
5. 用以下指令取得 chat ID：
   ```
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
6. 將 chat ID 填入 `TELEGRAM_CHAT_ID` 和 `TELEGRAM_ALLOWED_CHAT_IDS`

## 5. 設定銀行帳單篩選

```bash
cp config/banks.example.yaml config/banks.yaml
```

編輯 `config/banks.yaml`，設定各銀行的 Gmail 篩選條件和 PDF 密碼。

## 6. 啟動服務（Docker）

### 開發模式

```bash
docker compose up
```

首次啟動會自動：
- 驗證環境變數
- 檢查 OCR（tesseract）可用性
- 套用資料庫 migration
- 啟動 backend（API）、frontend（Vite dev server）、Redis

驗證服務正常：
```bash
curl http://localhost:8000/health
open http://localhost:5173
```

### Production 模式

適用於部署到遠端伺服器（詳見 [部署指南](deployment-guide.md)）：

```bash
docker compose -f docker-compose.yaml up -d --build
```

Production 模式僅啟動 backend、scheduler、bot、redis（不含 frontend），透過 Telegram bot 存取資料：
```bash
curl http://localhost:8000/health   # backend health check
```

## 7. 執行 Pipeline

### 完整執行
```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline
```

### 指定銀行
```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC
```

### 指定月份
```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --year 2026 --month 3
```

### 強制重新處理
```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --force --bank CTBC
```

### 指定階段執行
```bash
# 從 parse 階段開始到最後
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --from parse

# 只執行 ingest 到 parse
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --to parse

# 只重跑 decrypt 到 classify
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --from decrypt --to classify
```

Pipeline 階段順序：`ingest` → `decrypt` → `parse` → `classify` → `notify`

## 8. 查看報表

1. 開啟瀏覽器 http://localhost:5173（僅開發模式可用）
2. 使用 `.env` 中的 `API_TOKEN` 登入
3. 瀏覽各頁面：帳單列表、交易明細、分析圖表

## 9. 停止服務

```bash
docker-compose down
```

## 故障排除

### 服務未啟動
- 檢查 `.env` 是否齊全：`./scripts/check-env.sh`
- 檢查 Docker 是否運行：`docker info`
- 查看 logs：`docker-compose logs backend`

### Pipeline 執行失敗
- 確認 Gmail 憑證有效：重新執行 OAuth 認證
- 確認 PDF 密碼正確：檢查 `.env` 中的 `PDF_PASSWORD_<BANK_CODE>`
- 查看詳細 log：`docker-compose logs backend | grep ERROR`

### 前端無法載入資料
- 確認 backend 正常：`curl http://localhost:8000/health`
- 確認 API token 正確：登入時使用 `.env` 中的 `API_TOKEN`

### Telegram 通知未送達
- 確認 bot token 正確
- 確認 chat ID 正確
- 測試 bot 連線：`curl https://api.telegram.org/bot<TOKEN>/getMe`
