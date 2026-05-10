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
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token（從 @BotFather 取得） | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | Pipeline 通知目標 chat ID（見[第 4 節](#4-設定-telegram-bot)） | `123456789` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Bot 指令白名單 chat ID，逗號分隔 | `123456789,-1001234567890` |
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

### 建立 Bot

1. 在 Telegram 搜尋 `@BotFather`，輸入 `/newbot`，依指示建立 bot
2. 記下 bot token，填入 `.env` 的 `TELEGRAM_BOT_TOKEN`

### 取得 Chat ID

對 bot 傳送任意訊息後，執行 helper script：

```bash
./scripts/get-telegram-chat-id.sh
```

腳本會自動讀取 `.env` 中的 token 並列出所有聊天室 ID。也可直接帶入 token：

```bash
./scripts/get-telegram-chat-id.sh "123456:ABC-DEF..."
```

**群組 Chat ID**：將 bot 加入群組，在群組內傳送訊息，再執行腳本即可看到群組 ID（負數，例如 `-1001234567890`）。

> **注意**：若 bot 服務正在執行中（`docker compose up`），它正在以 long polling 模式接收訊息，會與此腳本搶 `getUpdates` 而導致拿不到結果。請先停止 bot 服務（`docker compose stop bot`），再執行腳本。

**替代方式**：在 Telegram 中對 `@userinfobot` 傳送訊息可取得個人 chat ID；對 `@RawDataBot` 傳送或轉發訊息可取得任意 chat ID。

### 填入 .env

| 變數 | 用途 | 範例 |
|------|------|------|
| `TELEGRAM_CHAT_ID` | Pipeline notify 階段傳送通知的目標聊天室 | `123456789` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 允許使用 bot 指令（`/status`、`/summary` 等）的聊天室白名單，逗號分隔 | `123456789,-1001234567890` |

- `TELEGRAM_CHAT_ID`：留空則 notify 階段不傳送 Telegram 通知，其他階段不受影響
- `TELEGRAM_ALLOWED_CHAT_IDS`：留空則所有 bot 指令被靜默忽略（bot 仍會啟動但不回應）
- 兩者可填不同值——例如通知發到個人私訊、但群組也能使用 bot 指令

## 5. 設定銀行帳單篩選

```bash
cp config/banks.example.yaml config/banks.yaml
```

編輯 `config/banks.yaml`，設定各銀行的 Gmail 篩選條件和 PDF 密碼。

> **注意**：`config/banks.example.yaml` 目前僅附 **CTBC / SINOPAC / FUBON** 3 家預設 block；其餘 ESUN / UBOT / CATHAY / TAISHIN 需依下方範例自行新增（bank_code 限制於 `config/bank-code-registry.yaml` 定義清單內）。

### 目前支援的銀行

| 銀行 | bank_code | Gmail filter 範例 | PDF 密碼環境變數 |
|------|-----------|-------------------|-----------------|
| 中國信託 | `CTBC` | `from:ebill@estats.ctbcbank.com subject:信用卡電子帳單` | `PDF_PASSWORD_CTBC` |
| 永豐銀行 | `SINOPAC` | `from:ebillservice@newebill.banksinopac.com.tw subject:永豐銀行信用卡 subject:電子帳單通知` | `PDF_PASSWORD_SINOPAC` |
| 玉山銀行 | `ESUN` | `from:estatement@esunbank.com subject:玉山銀行 subject:信用卡電子帳單` | `PDF_PASSWORD_ESUN` |
| 聯邦銀行 | `UBOT` | `from:estatement@ebillv2.card.ubot.com.tw subject:聯邦銀行信用卡 subject:電子帳單` | `PDF_PASSWORD_UBOT` |
| 國泰世華 | `CATHAY` | `from:service@pxbillrc01.cathaybk.com.tw subject:國泰世華銀行信用卡 subject:電子帳單` | `PDF_PASSWORD_CATHAY` |
| 台新銀行 | `TAISHIN` | `from:webmaster@bhurecv.taishinbank.com.tw subject:台新信用卡電子帳單` | `PDF_PASSWORD_TAISHIN` |
| 台北富邦 | `FUBON` | `from:rs@cf.taipeifubon.com.tw subject:台北富邦銀行 subject:信用卡帳單` | `PDF_PASSWORD_FUBON` |

### 新增玉山銀行設定

1. 在 `config/banks.yaml` 確認 ESUN 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_ESUN=你的身分證字號
   ```
3. Gmail filter 會自動匹配主旨格式為「玉山銀行YYYY年MM月信用卡電子帳單」的郵件

### 新增永豐銀行設定

1. 在 `config/banks.yaml` 確認 SINOPAC 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_SINOPAC=你的身分證字號
   ```
3. Gmail filter 會自動匹配主旨格式為「永豐銀行信用卡YYYY年MM月份電子帳單通知」的郵件

### 新增聯邦銀行設定

1. 在 `config/banks.yaml` 確認 UBOT 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_UBOT=你的身分證字號
   ```
3. Gmail filter 會自動匹配寄件者 `estatement@ebillv2.card.ubot.com.tw` 且主旨包含「聯邦銀行信用卡」+「電子帳單」的郵件

### 新增國泰世華銀行設定

1. 在 `config/banks.yaml` 確認 CATHAY 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_CATHAY=你的身分證字號
   ```
3. Gmail filter 會自動匹配寄件者 `service@pxbillrc01.cathaybk.com.tw` 且主旨格式為「國泰世華銀行信用卡YYYY年M月電子帳單」的郵件

### 新增台新銀行設定

1. 在 `config/banks.yaml` 確認 TAISHIN 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_TAISHIN=你的密碼
   ```
   密碼規則：身分證字號後 2 碼 + 生日月日 4 碼（共 6 碼）
3. （選用）若有舊期帳單使用不同密碼格式，可設定 legacy 密碼：
   ```bash
   PDF_PASSWORD_TAISHIN_LEGACY_1=舊密碼
   ```
   系統會依序嘗試主密碼 → legacy_1 → legacy_2 ...（最多 5 組），任一成功即完成解密。此機制適用於所有銀行，只需設定對應的 `PDF_PASSWORD_<BANK_CODE>_LEGACY_N` 環境變數。
4. Gmail filter 會自動匹配寄件者 `webmaster@bhurecv.taishinbank.com.tw` 且主旨格式為「台新信用卡電子帳單 YYYY年M月」的郵件

### 新增台北富邦銀行設定

台北富邦銀行帳單郵件有兩種格式：

- **格式 A**：郵件直接包含 PDF 附件（標準流程）
- **格式 B**：郵件僅包含「下載帳單明細」連結，需填寫身分證字號、民國生日及驗證碼後下載 PDF（web-fetch 流程）

兩種格式皆由同一 Gmail filter 匹配，系統會自動判斷並處理。

1. 在 `config/banks.yaml` 確認 FUBON 區塊已啟用（`is_active: true`）
2. 在 `.env` 新增 PDF 密碼：
   ```bash
   PDF_PASSWORD_FUBON=你的身分證字號
   ```
3. 在 `.env` 新增 web-fetch 憑證（格式 B 需要）：
   ```bash
   FUBON_NATIONAL_ID=你的身分證字號        # 格式 ^[A-Z][12]\d{8}$
   FUBON_ROC_BIRTHDAY=0881010              # 民國年月日 7 碼
   # 以下為選填 tuning knobs
   FUBON_CAPTCHA_MAX_RETRIES=7             # 預設 7；CAPTCHA + doLogin 迴圈最大重試次數
   FUBON_CAPTCHA_FALLBACK_LLM=false        # 預設 false；OCR 失敗後是否 fallback 至 Claude Vision
   ANTHROPIC_API_KEY=sk-ant-...            # 僅在 FUBON_CAPTCHA_FALLBACK_LLM=true 時需要
   ```
   民國生日格式為 7 碼：民國年 3 碼 + 月 2 碼 + 日 2 碼（例如民國 88 年 10 月 10 日 = `0881010`）
4. Gmail filter 會自動匹配寄件者 `rs@cf.taipeifubon.com.tw` 且主旨包含「台北富邦銀行」+「信用卡帳單」的郵件

### FUBON 手動下載步驟（SPA 自動化完成前的 fallback）

富邦網銀帳單系統已遷移為 SPA 架構，自動下載可能因驗證碼或 OTP 失敗。此時可改用手動下載：

1. 登入 [富邦網銀](https://www.taipeifubon.com.tw/) 或 [信用卡帳單服務](https://fbmbill.taipeifubon.com.tw/)
2. 下載當月 PDF 帳單
3. 將檔案命名為 `fubon-YYYY-MM.pdf`（例如 `fubon-2026-03.pdf`），月份格式有助自動配對
4. 放到手動下載目錄：
   - **本機開發**：`backend/data/manual-staging/FUBON/`
   - **Docker 環境**：host 的 `./backend/data/manual-staging/FUBON/` 對應容器內 `/data/manual-staging/FUBON/`
5. 執行 pipeline：
   ```bash
   docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON
   ```
6. Pipeline 會自動從手動目錄取得 PDF，處理完成後檔案會移至 `staging/FUBON/`

> **命名提示**：若目錄內只有一個 PDF，系統會直接取用，不要求特定檔名。若有多個 PDF 且無法依檔名判斷月份，pipeline 會報錯。

> **自訂目錄**：手動下載目錄可透過環境變數 `FUBON_MANUAL_STAGING_DIR` 覆蓋，預設為 `./data/manual-staging/FUBON`。

> **免責聲明**：FUBON web-fetch 流程會代表「使用者本人」登入富邦信用卡帳單系統，系統僅讀取「使用者本人郵件」中的下載連結、使用「使用者本人身分證號」與生日登入，並下載本期帳單 PDF。此為「使用者授權代理」行為，請勿將他人憑證填入 `.env`。
>
> **CAPTCHA 處理**：驗證碼由 ddddocr 在容器內本地辨識；rejected 樣本觸發重試，`FUBON_CAPTCHA_MAX_RETRIES` 預設 7 次。若在 `FUBON_CAPTCHA_FALLBACK_LLM=true` 下，rejected 樣本會轉送 Claude Vision 作為 fallback（需 `ANTHROPIC_API_KEY`）。production image 已預裝 `fubon-llm` extra（`anthropic` SDK），無須額外 rebuild 即可啟用 fallback。

**Troubleshooting — fetch 錯誤對應表**

| FetchError 訊息 | 意義 | 建議處理 |
| --- | --- | --- |
| `captcha_retry_exhausted: N attempts failed` | OCR 在 N 次重試後仍無法通過 `doLogin` | (a) 設 `FUBON_CAPTCHA_FALLBACK_LLM=true` + `ANTHROPIC_API_KEY` 啟用 Claude Vision fallback；(b) 暫時切換 manual staging，將 PDF 放到 `STAGING_DIR/FUBON/` 繞過 web-fetch |
| `record_not_found: doLogin msg='登入失敗, 查無資料'` | serial_key 已過期、或該期帳單已被抓取過 | 非憑證錯誤。正常情況下直接跳過即可；若剛送出新帳單信仍持續出現，確認 Gmail filter 是否抓到最新一封 |
| `credentials_wrong: doLogin ...` | 身分證 / 生日與富邦登錄不符 | 校對 `FUBON_NATIONAL_ID`、`FUBON_ROC_BIRTHDAY`（民國 7 碼） |
| `llm_fallback_unavailable: ...` | 已開啟 LLM fallback 但 SDK / API key 不可用 | 檢查 `ANTHROPIC_API_KEY` 是否有效；若為自建 image 且移除了 `fubon-llm` extra，需 rebuild backend image |

## 6. 啟動服務（Docker Compose）

```bash
docker compose up --build
```

`docker-compose.yaml` 一次啟動下列服務（皆使用 `target: production` build stage）：

| 服務 | 連接埠 | 說明 |
|------|--------|------|
| `backend` | `127.0.0.1:8000` | FastAPI + uvicorn |
| `worker` | — | RQ worker（Redis job queue） |
| `scheduler` | — | APScheduler 週期性任務 |
| `bot` | — | Telegram Bot daemon |
| `frontend` | `127.0.0.1:8080` | nginx 靜態站（已 build） |
| `redis` | `127.0.0.1:6379` | job queue + 快取 |

首次啟動 `backend` 時，`scripts/docker-entrypoint.sh` 會在容器內：
- 驗證環境變數（`scripts/check-env.sh`）
- 檢查 tesseract OCR 可用性
- 套用 alembic migration（`alembic upgrade head`）
- **自動 seed `bank_configs`**（讀取容器內唯讀 mount 的 `/config/banks.yaml` 與 `/config/bank-code-registry.yaml`）— 無需手動執行 `scripts/setup.sh`，重啟 container 會自動保持 idempotent。
- 啟動 uvicorn

驗證服務正常：
```bash
curl http://localhost:8000/health   # backend health check
open http://localhost:8080          # frontend 儀表板
```

> **僅需要伺服器端（不含 frontend）？** 用 `docker compose up backend worker scheduler bot redis`。遠端部署的完整流程見 [部署指南](deployment-guide.md)。

> **本地開發（熱更新）？** 若要使用 Vite dev server（port 5173）與 uvicorn reload，改用 `./scripts/start.sh`（不經 Docker），詳見 [開發者指南](developer-guide.md)。

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

1. 開啟瀏覽器 http://localhost:8080
2. 使用 `.env` 中的 `API_TOKEN` 登入
3. 瀏覽各頁面：帳單列表、交易明細、分析圖表

## 9. 停止服務

```bash
docker compose down
```

## 故障排除

### 服務未啟動
- 檢查 `.env` 是否齊全：`./scripts/check-env.sh`
- 檢查 Docker 是否運行：`docker info`
- 查看 logs：`docker compose logs backend`

### Pipeline 執行失敗
- 確認 Gmail 憑證有效：重新執行 OAuth 認證
- 確認 PDF 密碼正確：檢查 `.env` 中的 `PDF_PASSWORD_<BANK_CODE>`
- 查看詳細 log：`docker compose logs backend | grep ERROR`

### 舊期帳單解密失敗
- 若錯誤訊息顯示 `Invalid password (tried N candidates)`，表示所有候選密碼均無法解密
- 部分銀行（如 TAISHIN）過去可能變更過密碼規則，舊帳單需要舊密碼
- 在 `.env` 新增 `PDF_PASSWORD_<BANK_CODE>_LEGACY_1=舊密碼`，然後重跑 pipeline
- 最多可設定 5 組 legacy 密碼（`_LEGACY_1` 到 `_LEGACY_5`）

### FUBON fetch 失敗

- 若錯誤訊息包含 `manual_staging_empty`：表示 SPA 自動下載失敗且手動目錄無檔案。請依照「FUBON 手動下載步驟」放入 PDF 後重試
- 若錯誤訊息包含 `manual_staging_ambiguous`：手動目錄有多個 PDF 無法判斷月份。請保留單一檔案或以 `fubon-YYYY-MM.pdf` 命名
- 手動目錄位置：`backend/data/manual-staging/FUBON/`（Docker 環境下 host 路徑）

### ���端無法載入資料
- 確認 backend 正常：`curl http://localhost:8000/health`
- 確認 API token 正確：登入時使用 `.env` 中的 `API_TOKEN`

### Telegram 通知未送達
- 確認 bot token 正確
- 確認 chat ID 正確：執行 `./scripts/get-telegram-chat-id.sh` 驗證
- 測試 bot 連線：`curl https://api.telegram.org/bot<TOKEN>/getMe`

### bank_configs 需要重新 seed

`config/banks.yaml` 或 `config/bank-code-registry.yaml` 變更後，讓 container 重跑 entrypoint 的 seed 步驟即可生效：

```bash
docker compose restart backend
```

若不想重啟整個 service，可在 container 內手動執行（等價於 entrypoint 內的呼叫）：

```bash
docker exec -it ccas-backend-1 uv run python -m ccas.tools.bank_configs --apply
```

seed 為 idempotent 設計：重跑不會破壞既有資料，輸出會顯示 `created=0 updated=N unchanged=M`。
Host 直接執行 `scripts/setup.sh` 的流程也使用同一條命令，靠環境變數 `BANK_CONFIG_DIR` 切換路徑；未設定時退回 `../config/...` 相對路徑。

### 交易分類全部為「未分類」

如果 `/transactions` 頁面或 `/api/transactions` 回應中 `category` 全為 `未分類`，最常見的原因是 `categories` 資料表為空或缺少對應 keyword。`config/categories.yaml` 是分類關鍵字的 **SSOT（Single Source of Truth）**，修改後請擇一方式重跑 seed：

```bash
# 方案一：重啟 backend，entrypoint 會自動重跑 seed
docker compose restart backend

# 方案二：在 container 內手動執行
docker exec -it ccas-backend-1 uv run python -m ccas.tools.categories --apply
```

seed 策略：YAML 中存在的 keyword 會 UPSERT；使用者透過 API 額外新增的 keyword（不在 YAML 中）**不會**被 seed 流程刪除。若要調整分類，請以改 YAML 為優先。

seed 完成後需重跑 classify 階段讓歷史交易套用新規則：

```bash
docker exec -it ccas-backend-1 uv run python -m ccas.pipeline --from classify --to classify
```
