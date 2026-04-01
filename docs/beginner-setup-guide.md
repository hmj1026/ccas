# CCAS 新手上手指南

這份文件是給第一次碰 CCAS 的人看的。目標不是解釋所有內部設計，而是帶你從 0 開始，把 Gmail token 存到本機、申請 Telegram Bot、讓系統把信件附件抓到本地，最後在手機收到測試訊息，並在前端看到報表。

## 先講清楚目前狀態

CCAS 目前已經有這些能力：

- 可以讀取本地 Gmail OAuth token，使用 Gmail API 搜尋郵件並下載 PDF 附件到本地 staging 目錄。
- 可以把資料放進 SQLite，提供後端 API 與前端報表頁面。
- 可以透過 Telegram Bot API 發送訊息到你的手機。

但 repo 目前也有兩個限制：

- 目前已實作中國信託（CTBC）v1 parser；其他銀行的 parser 仍在開發中，真實銀行 PDF 需確認對應銀行 parser 是否已實作。
- `run_pipeline()` 目前不會自動送出「新帳單解析完成」通知，所以本文件用「直接送測試訊息」驗證 Telegram 收訊。

因此這份指南會分成兩段：

1. 真實 Gmail 流程：把 token 存本地、設定 Gmail/Telegram、成功把郵件附件抓到本地。
2. Demo 驗證流程：用 seed data 驗證前端報表與 Telegram 收訊。

## 1. 你需要先準備的東西

- 一個可登入 Google Cloud Console 的 Google 帳號
- 一個安裝 Telegram 的手機
- Python 3.12+
- `uv`
- Node.js 20+
- `pnpm`

如果你還沒有安裝 `uv` 和 `pnpm`，先處理好再往下做。

## 2. 建立基本設定檔

在 repo 根目錄建立後端用的 `.env`：

```bash
cp .env.example .env
```

先把 `.env` 裡這幾個值改掉：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
API_TOKEN=
GMAIL_CREDENTIALS_PATH=
GMAIL_TOKEN_PATH=
```

建議新手先用這組相對簡單的本機路徑：

```dotenv
GMAIL_CREDENTIALS_PATH=./data/credentials.json
GMAIL_TOKEN_PATH=./data/token.json
STAGING_DIR=./data/staging
API_TOKEN=replace-with-a-long-random-string
```

說明：

- `TELEGRAM_BOT_TOKEN`：等一下跟 BotFather 拿。
- `TELEGRAM_CHAT_ID`：等一下用 Telegram API 查。
- `TELEGRAM_ALLOWED_CHAT_IDS`：如果你之後要跑 bot command handler，這裡要填同一個 chat id。
- `API_TOKEN`：前端呼叫後端 API 會用到。
- `GMAIL_CREDENTIALS_PATH`：Google Cloud 下載的 `credentials.json` 要放在哪。
- `GMAIL_TOKEN_PATH`：你第一次授權完成後，本機會生成 `token.json` 的位置。

接著建立銀行設定 YAML：

```bash
cp config/banks.example.yaml config/banks.yaml
```

`config/banks.yaml` 是現在建議的新手入口，不需要再自己打 `curl` 去建立 `bank_configs`。  
可用的 `bank_code` 請看 [Bank Code 對照表](./bank-codes.md)。

最小範例：

```yaml
banks:
  - bank_code: CTBC
    gmail_filter: "from:service@ctbcbank.com subject:信用卡"
    active_parser_version: v1
    is_active: true
```

CTBC 電子帳單 PDF 有密碼保護，**必須在 `.env` 加入 PDF 密碼，否則解密階段會全數失敗**：

```dotenv
# CTBC PDF 密碼（通常是身分證字號，依申辦方式而定）
PDF_PASSWORD_CTBC=你的密碼
```

密碼格式由銀行決定，常見選項：身分證字號、出生年月日（YYYYMMDD）。若不確定請登入網銀確認或聯絡 CTBC 客服。

## 3. 申請 Gmail API 憑證並下載 `credentials.json`

1. 打開 Google Cloud Console。
2. 建一個新的 project。
3. 在這個 project 裡啟用 Gmail API。
4. 建立 OAuth consent screen。
5. 建立 OAuth Client ID。
6. Application type 選 Desktop app。
7. 下載 JSON 檔。

把下載下來的檔案放到 `backend/data/credentials.json`：

```bash
mkdir -p backend/data
cp /你的下載路徑/credentials.json backend/data/credentials.json
```

如果你想放別的位置，記得同步修改 `.env` 裡的 `GMAIL_CREDENTIALS_PATH`。

## 4. 第一次授權，產生本地 `token.json`

repo 現在已經有簡化入口，不需要手打 OAuth 指令。

先安裝後端依賴：

```bash
cd backend
uv sync
```

如果你只想單獨做這一步，可以執行：

```bash
uv run python -m ccas.tools.gmail_auth
```

這個流程會做的事：

- 開一個本機瀏覽器授權頁面
- 要你登入 Google 帳號
- 取得 Gmail readonly 權限
- 把 token 存成 `backend/data/token.json`

做完請確認：

```bash
ls -l data/credentials.json data/token.json
```

你應該看得到兩個檔案都存在。

如果之後 token 過期，CCAS 在讀取 Gmail 時會自動 refresh；如果 refresh 失敗，刪掉 `data/token.json` 重新做一次本節即可。

## 5. 申請 Telegram Bot

### 5.1 用 BotFather 建 bot

1. 在 Telegram 搜尋 `@BotFather`
2. 輸入 `/newbot`
3. 按提示給 bot 一個名稱與 username
4. 記下 BotFather 回傳的 token

把它填進 repo 根目錄 `.env`：

```dotenv
TELEGRAM_BOT_TOKEN=貼上你的 bot token
```

### 5.2 取得你的 chat id

1. 在 Telegram 打開你剛建立的 bot
2. 按 `Start` 或傳任意一則訊息給它
3. 用瀏覽器打開：

```text
https://api.telegram.org/bot<你的-bot-token>/getUpdates
```

4. 在回傳 JSON 裡找到 `message.chat.id`

把它填進 `.env`：

```dotenv
TELEGRAM_CHAT_ID=你的 chat id
TELEGRAM_ALLOWED_CHAT_IDS=你的 chat id
```

`TELEGRAM_CHAT_ID` 是主動推播用的目的地。  
`TELEGRAM_ALLOWED_CHAT_IDS` 是之後如果你要跑 bot command handler 時，用來做白名單驗證。

## 6. 第一次初始化整個本機流程

如果你希望少記命令，直接回 repo 根目錄執行：

```bash
./scripts/setup.sh
```

這支 script 會依序做：

- 檢查 `.env`
- 檢查 `config/banks.yaml`
- 檢查 `credentials.json`
- 產生或確認 `token.json`
- 套用資料庫 migration
- 預覽 bank configs 同步內容
- 把 `config/banks.yaml` 寫入資料庫

如果中間失敗，script 會直接停下來，並告訴你缺了哪個檔案或環境變數，還有應該怎麼修。

## 7. 啟動後端與資料庫

初始化完成後，回 repo 根目錄執行：

```bash
./scripts/start.sh
```

看到伺服器起來後，另開一個終端測試：

```bash
curl http://127.0.0.1:8000/health
```

應該回：

```json
{"status":"ok"}
```

再測一次需要 Bearer token 的 API：

```bash
curl \
  -H "Authorization: Bearer replace-with-a-long-random-string" \
  http://127.0.0.1:8000/api/overview
```

如果你有正確填 `API_TOKEN`，這個請求不應該回 401。

## 8. 執行一次 pipeline，確認信件附件有落到本地並解析成功

因為目前沒有完整 worker 流程給新手一鍵跑，最簡單的方式是直接用 CLI：

```bash
cd backend
uv run python -m ccas.pipeline
```

### Pipeline CLI 參數

Pipeline 支援以下可選參數，可組合使用：

```bash
# 僅處理指定銀行
uv run python -m ccas.pipeline --bank CTBC

# 僅處理指定月份（自動以 Gmail 日期篩選縮小搜尋範圍）
uv run python -m ccas.pipeline --bank CTBC --year 2026 --month 3

# 強制重新下載與重新解析（繞過去重機制）
uv run python -m ccas.pipeline --force --bank CTBC

# 全部銀行強制重新處理
uv run python -m ccas.pipeline --force
```

| 參數 | 說明 |
|------|------|
| `--force` | 繞過去重，重新下載已存在的附件、重新解析已存在的帳單 |
| `--bank BANK_CODE` | 僅處理指定銀行（如 `CTBC`） |
| `--year YYYY` | 以 Gmail 日期篩選限制年份 |
| `--month MM` | 以 Gmail 日期篩選限制月份（1-12） |

預設不帶任何參數時，pipeline 會處理所有啟用中的銀行，並自動跳過已下載的附件與已解析的帳單。

你要看的是三個結果：

### 8.1 本地 staging 目錄有檔案

```bash
find data/staging -type f | wc -l
```

如果 Gmail filter 有找到信件，而且信裡有 PDF 附件，你會看到檔案落在這裡。

### 8.2 pipeline 摘要裡 ingest 有數字

CLI 會輸出 JSON。重點看：

- `stages[].stage == "ingest"` 的 `counts.staged > 0`：代表從 Gmail 成功下載了 PDF
- `stages[].stage == "decrypt"` 的 `counts.decrypted > 0`：代表解密成功
- `stages[].stage == "parse"` 的 `counts.parsed > 0`：代表解析成帳單資料成功

如果 `staged > 0` 但 `decrypted == 0`，通常是密碼未設定（見第 2 節 `PDF_PASSWORD_CTBC`）。

### 8.3 確認資料庫已有帳單記錄

```bash
# 必須在 backend/ 目錄下執行
cd backend
uv run python -c "
from sqlalchemy import text, create_engine
engine = create_engine('sqlite:///data/ccas.db')
with engine.connect() as conn:
    rows = conn.execute(text('SELECT status, COUNT(*) FROM staged_attachments GROUP BY status')).fetchall()
    print('staged_attachments:', {status: count for status, count in rows})
    bills = conn.execute(text('SELECT bank_code, billing_month, total_amount FROM bills')).fetchall()
    for b in bills:
        print(f'  {b[0]} {b[1]} NT\${b[2]:,}')
"
```

如果 `bills` 有資料，代表整條鏈路（Gmail → decrypt → parse）已完全打通。

## 9. 真實 Gmail 路徑目前為什麼還不會直接出報表

這不是你操作錯，是目前 repo 的狀態：

- PDF 下載後會進到 staging
- 解密需要設定 `PDF_PASSWORD_<BANK_CODE>`（見第 2 節）
- 目前已實作中國信託（CTBC）v1 parser；其他銀行尚未實作
- 非 CTBC 的真實銀行 PDF 目前不會自動解析成 `bills` 和 `transactions`

如果你此刻的目標是驗證「前端報表能不能看」與「手機能不能收到訊息」，請走下一段 demo 驗證流程。

## 10. 用 seed data 驗證報表

注意：這一步會清掉現有資料，重建 demo 資料。  
如果你不想覆蓋資料庫，先備份 `backend/data/ccas.db`。

在 `backend/` 執行：

```bash
uv run python scripts/seed.py
```

這會建立：

- bank configs
- categories
- 1 筆 bill
- 5 筆 transactions

做完後，再測一次 overview API：

```bash
curl \
  -H "Authorization: Bearer replace-with-a-long-random-string" \
  "http://127.0.0.1:8000/api/overview?month=2026-03"
```

這次你應該會看到有金額資料，而不是空資料。

## 11. 啟動前端並打開報表

前端透過 Vite 的 `envDir: '..'` 設定，直接讀取專案根目錄的 `.env`。
請確認根目錄 `.env` 中這行已取消註解並填入正確值：

```dotenv
VITE_API_BASE=http://127.0.0.1:8000
```

登入前端時，直接在登入頁輸入 `.env` 裡的 `API_TOKEN` 即可，前端會向 backend 換成 httpOnly session cookie，不再把 token 打包進前端程式碼。

安裝與啟動：

```bash
cd frontend
pnpm install
pnpm dev
```

打開瀏覽器：

```text
http://127.0.0.1:5173
```

建議至少檢查這幾頁：

- `/overview`：看本月總覽卡片與即將到期帳單
- `/analytics`：把月份切到 `2026-03`，看月趨勢、類別分布、銀行比較
- `/bills`：看帳單列表
- `/transactions`：看消費明細
- `/settings`：看銀行設定與分類關鍵字

如果你已經先跑過 seed script：

- `/analytics` 在切到 `2026-03` 後應該有資料
- `/bills` 與 `/transactions` 應該能看到 demo 資料
- `/overview` 若未顯示資料，是因為它預設抓當月；seed script 固定寫入的是 `2026-03`

## 12. 驗證手機真的收得到 Telegram 訊息

因為目前 pipeline 不會自動送「新帳單解析完成」通知，所以最直接的驗證方式是送一則測試訊息。

在 `backend/` 執行：

```bash
uv run python - <<'PY'
import asyncio
from ccas.bot.client import send_message
from ccas.config import get_settings

async def main():
    settings = get_settings()
    await send_message(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        "CCAS 測試訊息：如果你看到這則，代表 Telegram 推播鏈路已經通了。"
    )

asyncio.run(main())
PY
```

如果手機有收到，代表這幾件事都沒問題：

- `TELEGRAM_BOT_TOKEN` 正確
- `TELEGRAM_CHAT_ID` 正確
- Bot 可以對你的聊天送訊息
- CCAS 的 Telegram client 可正常工作

## 13. 你現在應該完成了什麼

做到這裡，代表你已經完成：

- Gmail OAuth credentials 與 token 已經存到本地
- Telegram Bot 已建立完成
- backend API 已能啟動
- CCAS 已能用 Gmail filter 把附件抓到本地 staging
- 前端報表頁面已能成功載入
- 手機已能收到 CCAS 發出的 Telegram 測試訊息

## 14. 常見問題

### `Token 檔案不存在`

代表 `GMAIL_TOKEN_PATH` 指到的檔案不存在。  
回到第 4 節，重新產生 `token.json`。

### Gmail 抓不到信

通常有三種原因：

- `gmail_filter` 寫錯
- 你授權的 Google 帳號不是收那封信的帳號
- 郵件裡沒有 PDF 附件

先直接去 Gmail 網頁版，把同一段搜尋條件貼進搜尋框測試。

### 後端 API 一直 401

確認兩件事：

- `.env` 裡的 `API_TOKEN`
- 你在前端登入頁輸入的 token，或 `curl` header 裡帶的 token

這兩邊要一致。

### 前端打不開資料

先確認：

- backend 還活著
- `VITE_API_BASE=http://127.0.0.1:8000`
- `.env` 的 `FRONTEND_ORIGINS` 包含你的前端來源（預設已含 `http://127.0.0.1:5173`）
- 你已在前端登入頁輸入正確的 `API_TOKEN`

### Telegram 沒收到訊息

優先檢查：

- 你有沒有先在 Telegram 對 bot 按 `Start`
- `TELEGRAM_CHAT_ID` 有沒有填錯
- bot token 有沒有貼錯
- 你的手機 Telegram 有沒有把 bot 對話靜音

### 解密失敗：`Password not found in settings`

代表 `.env` 裡缺少對應銀行的 PDF 密碼。

1. 在 `.env` 補上密碼，格式為 `PDF_PASSWORD_<BANK_CODE>`：

   ```dotenv
   PDF_PASSWORD_CTBC=你的密碼
   ```

2. 把 `decrypt_failed` 的記錄重置為 `staged`，才能讓下次 pipeline 重試：

   ```bash
   # 必須在 backend/ 目錄下執行
   cd backend
   uv run python -c "
   from sqlalchemy import text, create_engine
   engine = create_engine('sqlite:///data/ccas.db')
   with engine.begin() as conn:
       conn.execute(
           text('UPDATE staged_attachments SET status=:s, error_reason=NULL WHERE status=:f'),
           {'s': 'staged', 'f': 'decrypt_failed'},
       )
   with engine.connect() as conn:
       n = conn.execute(text(\"SELECT COUNT(*) FROM staged_attachments WHERE status='staged'\")).scalar()
       print(f'重置完成，待解密: {n} 筆')
   "
   ```

3. 重新執行 pipeline（兩種方式皆可）：

   ```bash
   # 方式 A：一般模式（需要先做上面的重置步驟）
   uv run python -m ccas.pipeline

   # 方式 B：force 模式（自動繞過去重，不需手動重置）
   uv run python -m ccas.pipeline --force --bank CTBC
   ```

### 為什麼 Gmail 附件抓到了，前端還是沒有真實帳單資料

目前已實作中國信託（CTBC）v1 parser。若你使用的不是 CTBC 帳單，該銀行的 parser 可能尚未實作。
你可以先用 seed data 驗證前端與通知鏈路，或等待對應銀行 parser 補上後再接回真實 Gmail 帳單。
