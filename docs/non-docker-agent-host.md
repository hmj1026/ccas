# 無 Docker 的 Agent Host

本文件說明在不啟動 Docker Compose 的主機上使用 CCAS Agent MCP。先分清楚
兩種用途：只提供 MCP 查詢時，主機只需要 Python、uv、CCAS backend 與可讀取的
SQLite 資料庫；要執行背景 pipeline 時，才需要 Redis、RQ worker 與 scheduler。
前者不需要 Node.js、pnpm、frontend 或 Redis。

MCP server 使用本機 `stdio`，不會自行啟動 API、worker、scheduler 或 Redis。它會
讀取 `DATABASE_URL` 指向的資料庫，因此資料庫必須已由既有 CCAS 安裝產生，或先
完成 migration 與登入資料準備。

## MCP-only 最小安裝

### 1. 準備 Python 與 backend

需求是 Python 3.12+ 與 [uv](https://docs.astral.sh/uv/)。在主機上執行：

```bash
git clone https://github.com/hmj1026/ccas.git
cd ccas
cp .env.example .env
cd backend
uv sync --frozen
```

直接以 `uv` 啟動時，`API_TOKEN` 必須存在於環境或 `.env`；MCP 不使用 API
endpoint，但共用同一套設定仍會要求此欄位：

```bash
export API_TOKEN="$(openssl rand -hex 32)"
```

若這是新資料庫，先建立資料目錄並執行 migration：

```bash
mkdir -p data
uv run alembic upgrade head
```

若資料庫已由既有 CCAS 安裝建立，確認 `.env` 中的 `DATABASE_URL` 指向該資料庫，
並跳過 migration。相對路徑是以 `backend/` 為目前工作目錄解析；需要固定位置時，
請改成絕對路徑。

### 2. 啟動與設定 MCP client

先用前景程序確認 server 可以啟動；它是長駐的 stdio 程序，不會顯示互動提示，按
`Ctrl-C` 結束：

```bash
uv run ccas-mcp
```

MCP client 使用絕對路徑設定 `backend/`：

```json
{
  "mcpServers": {
    "ccas": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/ccas/backend",
        "ccas-mcp"
      ]
    }
  }
}
```

client 不支援 `--directory` 時，改用工作目錄
`/absolute/path/to/ccas/backend`，command 使用 `uv run ccas-mcp`。不要把 stdout
導向 log、加入 shell banner 或 debug print；stdout 只允許 MCP JSON 訊息，診斷訊息
會走 stderr。

### 3. 最小 smoke check

在 MCP client 中依序確認：

1. `tools/list` 回傳六個唯讀 tools。
2. 第一個實際查詢呼叫 `get_payment_due`，它不需要參數，也不需要 Redis、API 或
   frontend。沒有帳單時，收到空的 `data` 或可理解的業務結果即可。
3. 再呼叫 `list_bills` 或 `pipeline_status`，確認 client 讀到的是目標資料庫。

如果 tools discovery 失敗，先在 `backend/` 執行 `uv sync --frozen` 並確認 client
設定的絕對路徑。若 discovery 成功但資料為空，檢查 `DATABASE_URL`、資料庫檔案
權限與目前工作目錄。

## 需要背景 pipeline 時的 Redis

MCP-only 不需要 Redis。worker 會從 Redis 取 RQ job，scheduler 會把週期性工作放
入同一個 queue；只有啟動這兩個程序時才需要在 host 管理 Redis。使用 loopback
連線並在 `.env` 設定：

```dotenv
REDIS_URL=redis://localhost:6379/0
```

### Linux（systemd）

Ubuntu/Debian 套件名稱通常是 `redis-server`：

```bash
sudo apt-get update
sudo apt-get install redis-server redis-tools
sudo systemctl enable --now redis-server
redis-cli ping
```

預期輸出是 `PONG`。若發行版使用不同 unit 名稱，查詢並啟動 `redis.service`：

```bash
systemctl list-unit-files '*redis*'
sudo systemctl enable --now redis
```

### macOS（Homebrew）

```bash
brew install redis
brew services start redis
redis-cli ping
```

預期輸出是 `PONG`。查看狀態：

```bash
brew services list | grep redis
```

`systemctl` 不存在於 macOS；不要用 Linux 的 systemd 指令管理 Homebrew Redis。
若 Redis 啟用密碼，將完整連線字串（例如
`redis://:password@localhost:6379/0`）同步寫入 `REDIS_URL`，不要只設定
`REDIS_PASSWORD`。

## Frontend 的 Node、pnpm 與 Corepack

只有要在同一台 host 開發或提供 frontend 時才需要這一節。專案以 Node.js 22+
為標準；CI 與 Dockerfile 都使用 Node 22，Node 20 不在本專案支援範圍內。

```bash
node --version       # v22 或更新
corepack --version
cd frontend
corepack enable --install-directory "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
corepack install
pnpm --version       # 應符合 package.json 的 pnpm@10.33.4
pnpm install --frozen-lockfile
```

若 `corepack enable` 回報無法寫入 `/usr/local/bin` 或其他 system directory，使用
上面的 `--install-directory "$HOME/.local/bin"`，並把該目錄加入 shell 的 PATH。
也可以改用 nvm、asdf 或 Homebrew 安裝使用者自己的 Node，再重試 `corepack enable`；
不要用 sudo 把專案依賴寫進系統 Node 目錄。

## 問題定位

| 症狀 | 先檢查 |
|---|---|
| `uv: command not found` | 安裝 uv，或把 uv 的安裝目錄加入 PATH。 |
| `API_TOKEN` 缺少 | 在 backend/ 的 shell export，或寫入本機 `.env`；不要提交 `.env`。 |
| MCP client 顯示 JSON parse error | 確認 command 是 stdio，stdout 沒有 shell banner 或 debug print。 |
| tools 存在但查不到資料 | 確認 `DATABASE_URL`、資料庫檔案權限，以及 client 的 backend 路徑。 |
| worker/scheduler 連不上 queue | 確認 `REDIS_URL`、`redis-cli ping` 與 host service 狀態。 |
| macOS 沒有 `systemctl` | 使用 `brew services` 管理 Homebrew Redis。 |
| Corepack permission denied | 使用 `--install-directory "$HOME/.local/bin"` 並更新 PATH。 |

MCP 的 tools、資料投影與安全邊界仍以 [`mcp-installation.md`](mcp-installation.md)
為準；本文件只補充非 Docker host 的依賴與最小啟動路徑。需要常駐 worker 或
scheduler 時，請看 [無 Docker 的 Worker 與 Scheduler 維運](non-docker-host-services.md)。
