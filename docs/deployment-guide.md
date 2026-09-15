# CCAS 進階部署指南（自建 build）

> 📌 **終端使用者請改看 [docs/install-quickstart.md](install-quickstart.md)**。
>
> 本指南針對需要**自建 image / 客製化部署 / 從原始碼建置**的進階使用者：
> - 內網環境無法存取 GHCR
> - 需要修改 Dockerfile 或加私有依賴
> - 開發團隊建立 staging 環境
>
> 一般使用者只需下載 release 的 `docker-compose.yml` + `example.env` 即可，不需 clone repo。

本指南說明如何將 CCAS 部署到遠端伺服器或任何安裝了 Docker 的環境。

## 前置需求

- Docker Engine 24+ 和 **Docker Compose v2.24+**（`docker-compose.override.yml` 使用 `!override` YAML tag，舊版會 parse 失敗）
- 至少 2GB RAM（tesseract OCR 需要記憶體）
- Google Cloud 專案與 OAuth 憑證（執行 Gmail ingest 時需要）
- Telegram Bot token 和 Chat ID（啟用通知時需要）

驗證版本：

```bash
docker compose version  # 須顯示 v2.24 以上
```

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

編輯 `.env`，依要啟用的功能填入變數。詳見 [使用者手冊](user-guide.md#2-設定環境變數) 與 `.env.example`。

**self-build production 的必要邊界**：
- `API_TOKEN` 可省略；entrypoint 會自動產生並保存 token。
- `PUBLIC_BASE_URL` 只有在改用自訂網域／port 或需要 Gmail Web OAuth 時才需設定。
- `REPO_OWNER`、`CCAS_VERSION` 僅供 pull-only compose 使用，根目錄 self-build compose 不讀取它們。

> `API_TOKEN` **可不填**：entrypoint 首啟會自動生成 32-byte token 並落地至
> `/data/secrets/api-token`（root self-build host 對應 `backend/data/secrets/api-token`，檔案權限 0600），即可用該 token 登入 Web UI。

本指南的 self-build frontend 直接以 HTTP 提供服務；若未在前方配置 TLS，請在 `.env`
設 `API_COOKIE_SECURE=false`。正式 HTTPS 入口請維持 `true`。

## 3. Gmail 憑證

Production 模式使用 bind mount `./backend/data:/data` 儲存資料（見 `docker-compose.yaml`）。需將 Google OAuth 憑證放入 host 端的 `./backend/data/` 目錄。

**首次設定**：依 [Gmail 設定指南](gmail-setup.md) 使用 Web flow；若使用 CLI fallback，先取得 `token.json`，再將憑證複製到伺服器：

```bash
# 確保目錄存在
mkdir -p backend/data

# 將憑證複製到 backend/data/
cp /path/to/credentials.json backend/data/credentials.json
cp /path/to/token.json backend/data/token.json
```

注意：憑證必須是**檔案**（非目錄）。`token.json` 會由 Gmail API 自動更新。

## 4. 銀行設定

編輯 `config/banks.yaml`，設定各銀行的 Gmail 篩選條件。在 `.env` 中設定對應的 PDF 密碼：

```
PDF_PASSWORD_CTBC=your-ctbc-password
```

## 5. 啟動 Production 服務

```bash
docker compose -f docker-compose.yaml up -d --build
```

此指令僅使用 base `docker-compose.yaml`（不合併 override），以 production 模式啟動：
- **backend**: uvicorn + tesseract OCR（port 8000）+ alembic + seed bootstrap
- **worker**: RQ 2.x worker，跑 pipeline / classifier / notifier 工作
- **scheduler**: APScheduler cron + heartbeat writer（`/data/scheduler-heartbeat`）
- **bot**: Telegram long polling（未填 token 則 disabled idle）
- **frontend**: nginx static，直接暴露 `127.0.0.1:8080`（self-build 不含 proxy）
- **redis**: 非同步工作佇列（RQ + APScheduler 共用）

> release pull-only 部署（`docker/docker-compose.yml`）多一個 `proxy`（nginx reverse proxy），統一以 `${CCAS_PORT}` 對外、`/api → backend`、`/ → frontend`。本指南的 self-build 路徑由 `frontend` 直接對外，不掛 proxy。

### 強烈建議：設定 `COMPOSE_FILE` 鎖定 base compose

為避免維運人員在 production host 不小心執行裸 `docker compose up`（會自動載入 `docker-compose.override.yml` 進入 dev 模式，啟用 bind mount 與 DEBUG log），**請在 production host 的 shell profile 或 `.env` 加上**：

```bash
# /etc/profile.d/ccas.sh 或 ~/.bashrc
export COMPOSE_FILE=docker-compose.yaml
```

設定後 Compose 會忽略 override 自動發現；維運指令仍建議保留明確的 `-f docker-compose.yaml`，讓實際使用的 compose 檔可被檢查。

## 6. 驗證服務

```bash
# backend health check
curl http://127.0.0.1:8000/health

# 檢查 OCR 可用性
docker exec ccas-backend-1 python -c \
  "from ccas.parser.ocr import is_ocr_available; print('OCR:', is_ocr_available())"

# 查看所有服務狀態
docker compose -f docker-compose.yaml ps
```

## 7. 查看 Logs

```bash
# 所有服務
docker compose -f docker-compose.yaml logs -f

# 特定服務
docker compose -f docker-compose.yaml logs -f backend
docker compose -f docker-compose.yaml logs -f scheduler
```

啟動時應看到：
```
==> 驗證環境變數
==> 檢查 OCR 可用性
[INFO] tesseract OCR 已安裝: tesseract x.x.x
==> 套用資料庫 migration
==> 啟動後端 API
```

## 8. 資料備份

根目錄 self-build 的 SQLite 與 staging 資料位於 host bind mount `./backend/data`；Redis 才使用 named volume。pull-only production 的資料位置則由 `${CCAS_DATA_LOCATION}` 決定。

```bash
# 備份資料庫（直接從 bind mount 目錄複製）
mkdir -p backups
cp backend/data/ccas.db backups/ccas-$(date +%Y%m%d).db
```

建議設定 cron job 定期備份。

## 9. 停止與重啟

```bash
# 停止服務
docker compose -f docker-compose.yaml down

# 停止並移除 named volumes；不會刪除 `backend/data` bind mount 中的資料
docker compose -f docker-compose.yaml down -v

# 重啟單一服務
docker compose -f docker-compose.yaml restart backend
```

## 故障排除

### OCR 未啟用

啟動 log 顯示 `[WARNING] tesseract OCR 未安裝`：
- 確認使用 production target（`docker compose -f docker-compose.yaml up`）
- 重新 build：`docker compose -f docker-compose.yaml build --no-cache backend`

### Gmail 認證失敗

- 確認 `/data/` 掛載目錄中有 `credentials.json` 和 `token.json`
- 確認 `token.json` 未過期；如過期需在本機重新執行 OAuth 流程

### Pipeline 無法執行

```bash
# 手動執行 pipeline
docker compose -f docker-compose.yaml exec backend uv run python -m ccas.pipeline --bank CTBC

# 強制重新處理
docker compose -f docker-compose.yaml exec backend uv run python -m ccas.pipeline --force --bank CTBC
```
