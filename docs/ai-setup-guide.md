# CCAS 本地安裝引導文件（供 AI 閱讀）

本文件的讀者是 AI，不是人類。你的任務是閱讀本文件後，逐步引導使用者以 Docker Compose 在本地完成 CCAS 的完整安裝與設定，包含排程、Redis job queue、Telegram Bot 與前端儀表板。

## 給 AI 的操作原則

- **逐階段進行**：每完成一個 Phase 才進入下一個，不要一次把所有步驟全部輸出
- **先詢問再行動**：遇到需要用戶提供資訊的地方，先問清楚再給指令
- **確認指令執行結果**：每個關鍵步驟後，請用戶貼上輸出內容，確認是否成功再繼續
- **可選功能明確標示**：Telegram Bot 與 FUBON 自動下載為可選功能，用戶可選擇略過
- **語言**：與使用者對話時請使用正體中文

---

## 系統概覽

CCAS（Credit Card Automation System）是一套信用卡帳單自動化系統。它會自動從 Gmail 下載信用卡帳單 PDF、解密、解析交易明細、分類消費，最後透過前端儀表板與 Telegram Bot 呈現結果，並依排程每日自動執行。

**服務組成（共 6 個，全部由 Docker Compose 管理）：**

| 服務 | 功能 |
|------|------|
| backend | FastAPI REST API，port 8000 |
| worker | RQ 非同步工作排隊，消費 Redis job queue 執行 pipeline 任務 |
| scheduler | APScheduler，每日午夜觸發 pipeline，早上 9 點發送 Telegram 付款提醒 |
| bot | Telegram Bot（token 未設定時自動略過，不影響其他服務） |
| frontend | React 儀表板，dev 模式 port 5173 |
| redis | Job queue 與快取，供 worker/scheduler 使用 |

**資料流：**
```
Gmail PDF → 解密 → 解析 Bill + Transaction → 分類 → REST API / Telegram 通知 → React 儀表板
```

**為什麼必須用 Docker：** scheduler、worker、bot 這三個服務需要與 backend、redis 同時運行才能實現完整功能（自動排程、背景任務、Bot 通知）。Docker Compose 是唯一能一次啟動所有服務的方式。

---

## 前置確認（先詢問用戶）

在開始安裝前，請先詢問用戶以下問題：

**問題 1：作業系統**
- macOS
- Linux（Ubuntu / Debian / 其他）
- Windows（必須先啟用 WSL2，所有指令在 WSL2 終端機內執行）

**問題 2：使用哪些銀行信用卡**（可複選）

支援銀行：中國信託（CTBC）、永豐（SINOPAC）、玉山（ESUN）、台新（TAISHIN）、聯邦（UBOT）、國泰（CATHAY）、富邦（FUBON）

這個答案決定需要設定哪些 `PDF_PASSWORD_*` 環境變數。

**問題 3：是否設定 Telegram Bot（強烈建議，用於帳單到期提醒）**
- 是：需要申請 Bot token 並設定 chat_id，scheduler 每日早上 9 點會推送付款提醒
- 否：跳過 Telegram 相關設定，自動提醒功能停用，其他功能（儀表板、排程 pipeline）正常

**問題 4：富邦卡自動下載（僅選擇了富邦時詢問）**
- 是：需要提供身分證字號與民國生日，系統會自動登入富邦網銀下載帳單
- 否：改用手動下載 PDF 後放入指定目錄的方式

---

## Phase 1：前置需求安裝

### 安裝 Docker

請用戶確認 Docker 與 Compose 版本：

```bash
docker --version
docker compose version
```

**預期輸出範例：**
```
Docker version 27.x.x
Docker Compose version v2.30.x
```

需求：Docker Engine 24+、Docker Compose v2.24+（注意是 `docker compose`，不是舊版的 `docker-compose`）

若尚未安裝，依作業系統指引：
- macOS：安裝 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（內含 Compose）
- Linux：執行 `curl -fsSL https://get.docker.com | sh` 安裝 Docker Engine，再安裝 Compose plugin
- Windows：安裝 Docker Desktop（內含 WSL2 整合）；所有後續指令在 WSL2 終端機內執行

### 安裝 Git

```bash
git --version
```

若未安裝：
- macOS：`brew install git` 或安裝 Xcode Command Line Tools
- Linux：`sudo apt-get install git`
- Windows WSL2：`sudo apt-get install git`

---

## Phase 2：取得程式碼

```bash
git clone <repository-url>
cd ccas
```

請告知用戶將 `<repository-url>` 替換為實際的 repo URL。

確認取得成功：

```bash
ls .env.example config/banks.example.yaml docker-compose.yaml
```

**預期輸出：** 三個檔案存在，無錯誤訊息。

---

## Phase 3：環境變數設定

### 複製範本

```bash
cp .env.example .env
cp config/banks.example.yaml config/banks.yaml
```

### 填入必填欄位

用任意文字編輯器開啟 `.env`（macOS/Linux 可用 `nano .env`），填入以下欄位：

**`API_TOKEN`（必填）**

這是登入前端儀表板的密碼，自訂任意字串即可：

```
API_TOKEN=你的自訂密碼
```

**各銀行 PDF 密碼（依所選銀行填入）**

信用卡電子帳單 PDF 通常有密碼保護。密碼依銀行規則不同，常見為身分證末 4 碼、生日、卡號末 4 碼等。請向用戶確認每張卡的 PDF 密碼：

```
PDF_PASSWORD_CTBC=你的中信PDF密碼
PDF_PASSWORD_SINOPAC=你的永豐PDF密碼
PDF_PASSWORD_ESUN=你的玉山PDF密碼
PDF_PASSWORD_TAISHIN=你的台新PDF密碼
PDF_PASSWORD_UBOT=你的聯邦PDF密碼
PDF_PASSWORD_CATHAY=你的國泰PDF密碼
PDF_PASSWORD_FUBON=你的富邦PDF密碼
```

只填有使用的銀行即可，未設定的銀行帳單在解密階段會進入 `decrypt_failed` 狀態。

**富邦自動下載（選擇了富邦且要自動下載時）**

```
FUBON_NATIONAL_ID=A123456789
FUBON_ROC_BIRTHDAY=0881010
```

`FUBON_ROC_BIRTHDAY` 格式為民國年月日 7 碼，例如民國 88 年 10 月 10 日 = `0881010`。

**Telegram Bot（若用戶選擇設定，在 Phase 5 完成後回來填入）**

```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
```

目前先留空，Phase 5 完成後再填入。若不設定，這三個變數保持空值，bot 服務啟動時會自動略過，不影響其他服務。

### 驗證環境變數

```bash
./scripts/check-env.sh
```

**預期輸出：** `All required environment variables are set.`（或類似的成功訊息）

若有缺漏的必填欄位，腳本會列出缺少的變數名稱，請協助用戶補全後再次執行。

---

## Phase 4：Google OAuth 設定（Gmail API）

系統需要 Gmail API 授權才能自動下載帳單附件。這個步驟需要建立 Google Cloud 專案並取得 OAuth 憑證。

### 步驟 4-1：建立 Google Cloud 專案

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)，以接收帳單的 Gmail 帳號登入
2. 點擊左上角專案選單 → 「新增專案」
3. 專案名稱填入 `ccas`，點擊「建立」

### 步驟 4-2：啟用 Gmail API

1. 左側選單 → 「API 和服務」→「程式庫」
2. 搜尋 `Gmail API`，點入後按「啟用」

### 步驟 4-3：設定 OAuth 同意畫面

1. 左側選單 → 「API 和服務」→「OAuth 同意畫面」
2. 使用者類型選「**外部**」→「建立」
3. 填入應用程式名稱（例如：`CCAS`）、使用者支援電子郵件（填自己的 Gmail）
4. 捲到底部，「開發人員聯絡資訊」也填自己的 Gmail，點「儲存並繼續」
5. 「範圍」頁直接點「儲存並繼續」
6. 「測試使用者」頁 → 點「新增使用者」→ 填入自己的 Gmail → 儲存

### 步驟 4-4：建立 OAuth 憑證

1. 左側選單 → 「API 和服務」→「憑證」
2. 點擊「建立憑證」→「OAuth 用戶端 ID」
3. 應用程式類型選「**電腦版應用程式**」
4. 名稱填入 `ccas-desktop`，點擊「建立」
5. 點擊「下載 JSON」，儲存到本機

### 步驟 4-5：放置憑證檔案

```bash
# 建立 data 目錄（若不存在）
mkdir -p backend/data

# 將下載的 JSON 檔案複製到指定位置
cp /path/to/downloaded-credentials.json backend/data/credentials.json
```

請用戶把實際下載路徑替換 `/path/to/downloaded-credentials.json`。

確認檔案存在：

```bash
ls backend/data/credentials.json
```

### 步驟 4-6：在 Docker 容器內執行 Gmail OAuth 授權

先做初步 image build（只需 build backend）：

```bash
docker compose build backend
```

執行 OAuth 授權（容器內執行，token 存入 backend/data/）：

```bash
docker compose run --rm backend uv run python -m ccas.tools.gmail_auth
```

這個指令會輸出一個 URL，請用戶複製後貼入瀏覽器，以 Gmail 帳號登入並授權，授權完成後瀏覽器會顯示「This site can't be reached」或空白頁，這是正常行為（本機應用程式流程）。

若出現需要輸入驗證碼的提示，請用戶將瀏覽器網址列的完整 URL 複製回終端機貼上。

**確認授權成功：**

```bash
ls backend/data/token.json
```

**預期輸出：** 檔案存在。

---

## Phase 5：Telegram Bot 設定（可選）

若用戶選擇跳過，直接前往 Phase 6。`.env` 中 Telegram 相關三個變數保持空值即可。

若要設定：

### 步驟 5-1：建立 Bot 並取得 token

1. 在 Telegram 搜尋 `@BotFather`，開啟對話
2. 發送 `/newbot`
3. 依提示輸入 Bot 顯示名稱（例如：`我的帳單機器人`）
4. 輸入 Bot username（必須以 `bot` 結尾，例如：`my_ccas_bot`）
5. BotFather 回覆的 token 格式類似 `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`，複製保存

### 步驟 5-2：取得 chat_id

先在 Telegram 搜尋剛建立的 Bot username，向它發送任意訊息（例如：`hi`）。

然後執行：

```bash
./scripts/get-telegram-chat-id.sh
```

若腳本無輸出，代表 Bot 尚未收到訊息。請確認已向 Bot 發送過訊息，等待約 10 秒後再試。

### 步驟 5-3：填入 .env

開啟 `.env`，填入三個變數：

```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=你的chat_id（純數字）
TELEGRAM_ALLOWED_CHAT_IDS=你的chat_id（與上面相同；若多人共用，以逗號分隔）
```

---

## Phase 6：啟動所有服務

```bash
docker compose up --build
```

Docker Compose 會同時啟動全部 6 個服務：backend、worker、scheduler、bot（若有設定 token）、frontend、redis。

backend 容器啟動時會自動執行：
- `check-env`：驗證環境變數
- `alembic upgrade head`：建立資料庫表格（首次執行）
- 同步銀行設定

**第一次執行**需要下載並建構 Docker image，可能需要 5~10 分鐘。之後啟動不需重新 build。

### 確認啟動成功

等待日誌穩定後，確認以下三行都出現：

```
ccas-backend-1    | INFO: Application startup complete.
ccas-frontend-1   | VITE v... ready in ...ms
ccas-redis-1      | Ready to accept connections tcp
```

確認 worker 與 scheduler 也已就緒：

```
ccas-worker-1     | Worker ... started
ccas-scheduler-1  | Scheduler started
```

若有設定 Telegram token，bot 也應有啟動訊息：

```
ccas-bot-1        | Application started
```

若 token 未設定，bot 服務日誌顯示跳過啟動，此為正常行為。

---

## Phase 7：驗證安裝

### 確認 API 健康狀態

開啟新的終端機視窗執行（保持 `docker compose up` 繼續運行）：

```bash
curl http://127.0.0.1:8000/health
```

**預期輸出：** `{"status":"ok"}`

### 確認前端儀表板可存取

請用戶在瀏覽器開啟 `http://localhost:5173`，應顯示登入頁面。

使用 `.env` 中設定的 `API_TOKEN` 值登入。登入後可看到帳單列表（目前為空，等待第一次 pipeline 執行後會有資料）。

### 確認排程器已設定任務

```bash
docker compose logs scheduler --tail=30
```

**預期輸出：** 包含以下兩行（代表排程已設定）：

```
Added job "daily_pipeline" to job store "default"
Added job "daily_payment_reminders" to job store "default"
```

### 確認 worker 正在監聽 Redis queue

```bash
docker compose logs worker --tail=10
```

**預期輸出：** 包含 `Listening on default...` 或 `Worker ... started`

### 手動觸發一次 Pipeline（驗證完整流程）

安裝完成後，建議立即手動觸發一次 pipeline 確認 Gmail 授權和帳單解析正常：

```bash
./scripts/pipeline.sh
```

觀察 backend 與 worker 日誌，確認沒有 OAuth 錯誤或嚴重錯誤。第一次執行會從 Gmail 下載最近的帳單附件並開始處理。

---

## Phase 8：安裝完成後的日常使用說明

告知用戶以下日常使用方式：

### 啟動與停止服務

```bash
# 啟動（前景，可看日誌）
docker compose up

# 啟動（背景執行）
docker compose up -d

# 停止
docker compose down
```

系統重開機後需手動重新執行 `docker compose up -d`，或依作業系統設定 Docker 開機自啟並加入 `restart: unless-stopped`（進階設定）。

### 自動排程（無需手動操作）

每日午夜，scheduler 服務自動：
1. 呼叫 API 觸發 pipeline
2. worker 接收任務，執行 5 階段：ingest → decrypt → parse → classify → notify
3. 從 Gmail 下載新帳單、解析交易明細、分類消費

每日早上 9 點，scheduler 自動查詢即將到期帳單，透過 Telegram Bot 發送付款提醒。

### 前端儀表板

瀏覽器開啟 `http://localhost:5173`，以 `API_TOKEN` 登入，可查看：
- 帳單列表與待繳金額
- 每筆交易明細與消費分類
- 各類別消費統計

### Telegram Bot 指令

若有設定 Telegram Bot，可向 Bot 發送以下指令：

| 指令 | 功能 |
|------|------|
| `/status` | 最新帳單狀態與待繳資訊 |
| `/upcoming` | 即將到期的帳單 |
| `/summary` | 帳單統計摘要 |
| `/category <分類名稱>` | 查看指定分類的交易 |
| `/paid` | 已繳款帳單列表 |

### 手動觸發 Pipeline

若要立即處理最新帳單而不等待排程（需服務在運行中）：

```bash
# 全部銀行
./scripts/pipeline.sh

# 指定銀行
./scripts/pipeline.sh --bank CTBC

# 強制重新處理（跳過重複檢查，例如修正 PDF 密碼後重跑）
./scripts/pipeline.sh --force
```

---

## 常見錯誤與處理

### Gmail OAuth token 過期或失效

**症狀：** backend 或 worker 日誌出現 `Token has been expired or revoked`、`invalid_grant` 等 OAuth 錯誤

**處理：** 重新執行 OAuth 授權

```bash
docker compose run --rm backend uv run python -m ccas.tools.gmail_auth
```

完成瀏覽器授權後，重啟相關服務：

```bash
docker compose restart backend worker scheduler
```

### PDF 密碼錯誤

**症狀：** 帳單狀態停在 `decrypt_failed`（可在前端儀表板 Staging 頁面查看）

**處理：**
1. 開啟 `.env`，確認對應銀行的 `PDF_PASSWORD_*` 值正確
2. 修正後重啟 backend 讓新設定生效：`docker compose restart backend`
3. 執行強制重新處理：

```bash
./scripts/pipeline.sh --force --bank <BANK_CODE>
```

### Telegram Bot 無回應

**症狀：** 向 Bot 發送指令後沒有任何回覆

**處理清單：**
1. 確認 `TELEGRAM_BOT_TOKEN` 格式正確（數字:英數字串）
2. 確認發訊息的 chat_id 已加入 `TELEGRAM_ALLOWED_CHAT_IDS`
3. 確認 bot 服務正在運行：

```bash
docker compose ps bot
docker compose logs bot --tail=20
```

若 bot 未啟動，確認 token 已填入 `.env` 後重啟：

```bash
docker compose restart bot
```

### Docker Compose 版本過舊

**症狀：** `docker compose up` 出現語法錯誤或 `override` 自動合併失效

**確認版本：**

```bash
docker compose version
```

需要 v2.24 以上。若版本過舊，請更新 Docker Desktop（macOS/Windows）或更新 Compose plugin（Linux）。

### Port 衝突

**症狀：** 啟動時出現 `Bind for 0.0.0.0:8000 failed: port is already allocated`

**處理：** 建立本機客製覆蓋檔案（已在 .gitignore 中，不會提交）：

```bash
cp docker-compose.local.yml.example docker-compose.local.yml
```

在 `docker-compose.local.yml` 中修改衝突的 host port（冒號左側的數字），例如將 backend 改用 8001：

```yaml
services:
  backend:
    ports:
      - "127.0.0.1:8001:8000"
```

啟動時加入此檔案：

```bash
docker compose -f docker-compose.yaml -f docker-compose.override.yml -f docker-compose.local.yml up --build
```

### 新增依賴後服務啟動報錯（ModuleNotFoundError）

**症狀：** 更新 `.env` 或設定後 backend 出現 import 錯誤

**處理：** 重新建構 image：

```bash
docker compose up -d --build backend worker scheduler bot
```

---

## 環境變數快速參考

| 變數 | 必填 | 說明 |
|------|------|------|
| `API_TOKEN` | 是 | 登入前端儀表板的密碼，自訂任意字串 |
| `GMAIL_CREDENTIALS_PATH` | 否 | credentials.json 路徑，Docker 自動掛載至 `/data/credentials.json` |
| `GMAIL_TOKEN_PATH` | 否 | token.json 路徑，Docker 自動掛載至 `/data/token.json` |
| `PDF_PASSWORD_CTBC` | 依需求 | 中信 PDF 密碼 |
| `PDF_PASSWORD_SINOPAC` | 依需求 | 永豐 PDF 密碼 |
| `PDF_PASSWORD_ESUN` | 依需求 | 玉山 PDF 密碼 |
| `PDF_PASSWORD_TAISHIN` | 依需求 | 台新 PDF 密碼 |
| `PDF_PASSWORD_UBOT` | 依需求 | 聯邦 PDF 密碼 |
| `PDF_PASSWORD_CATHAY` | 依需求 | 國泰 PDF 密碼 |
| `PDF_PASSWORD_FUBON` | 依需求 | 富邦 PDF 密碼 |
| `TELEGRAM_BOT_TOKEN` | 可選 | Bot token，空值時 Bot 服務不啟動 |
| `TELEGRAM_CHAT_ID` | 可選 | 通知目標 chat ID（純數字） |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 可選 | 允許使用 Bot 指令的 chat ID 白名單（逗號分隔） |
| `FUBON_NATIONAL_ID` | 可選 | 富邦自動下載用身分證字號 |
| `FUBON_ROC_BIRTHDAY` | 可選 | 富邦自動下載用民國生日（7 碼，例：`0881010`） |
| `REDIS_URL` | 否 | Docker 自動設為 `redis://redis:6379/0`，無需手動設定 |
| `DATABASE_URL` | 否 | Docker 自動設為 `/data/ccas.db`，無需手動設定 |
| `LOG_LEVEL` | 否 | 日誌等級（DEBUG / INFO / WARNING / ERROR），預設 `INFO` |
