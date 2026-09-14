# 無 Docker 的 Agent Host

本文件說明在不啟動 Docker Compose 的主機上使用 CCAS Agent MCP。先分清楚
兩種用途：只提供 MCP 查詢時，主機只需要 Python、uv、CCAS backend 與可讀取的
SQLite 資料庫；要執行背景 pipeline 時，才需要 Redis、RQ worker 與 scheduler。
前者不需要 Node.js、pnpm、frontend 或 Redis。

Grok／Cursor 家族 host 首選本機 loopback Streamable HTTP
（`http://127.0.0.1:8001/mcp`）。stdio 是仍必須 spawn 子行程的 client 後援。
兩個 adapter 都讀取 `DATABASE_URL` 指向的資料庫，因此資料庫必須已由既有 CCAS
安裝產生，或先完成 migration 與登入資料準備。HTTP 路徑不自行啟動 API、worker、
scheduler 或 Redis；`install mcp-http` 也會跳過 Redis。client 設定與排錯以
[`mcp-installation.md`](mcp-installation.md) 為 SSOT。

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

直接以 `uv` 啟動時，`API_TOKEN` 必須存在於環境或 `.env`。stdio 不把這個值當
Bearer；loopback HTTP MCP 會用同一個 token 做 `Authorization: Bearer`。不要把
真實 token 寫進 git 或 MCP 設定檔，client 範例用 `${env:API_TOKEN}`：

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

### 2. 啟動與設定 MCP client（首選 HTTP）

Grok／Cursor 家族請把 host 指到 URL，不要 spawn `ccas-mcp`。常駐用 supervisord
（systemd／launchd **不能**跑 `mcp-http`）：

```bash
cd /absolute/path/to/ccas
cd backend && uv sync --frozen --extra supervisor && cd ..
./scripts/host-services.sh --driver=supervisord install mcp-http
./scripts/host-services.sh --driver=supervisord smoke mcp-http
```

`install all` 在 supervisord 下也會安裝 `mcp-http`。沒有 supervisord 時，前景檢查：

```bash
uv run ccas-mcp-http
# 或：uv run python -m ccas.mcp.http
```

無 Bearer 打 `/mcp` 應為 HTTP 401。然後在 MCP client 寫入（不要填真實 token）：

```json
{
  "mcpServers": {
    "ccas": {
      "url": "http://127.0.0.1:8001/mcp",
      "headers": {
        "Authorization": "Bearer ${env:API_TOKEN}"
      }
    }
  }
}
```

若 host 需要顯式型別，加上 `"type": "streamable-http"`。完整片段與禁止事項見
[`mcp-installation.md`](mcp-installation.md)。

仍只能 spawn 子行程的 client，才用 stdio 後援：`uv run ccas-mcp`，command 為
`uv run --directory /absolute/path/to/ccas/backend ccas-mcp`。stdio 的 stdout
只允許 MCP JSON，診斷走 stderr。

### 3. 最小 smoke check

1. HTTP：無 Bearer 的 `http://127.0.0.1:8001/mcp` 回 401；有 token 的 client 能
   `tools/list`。
2. 第一個實際查詢呼叫 `get_payment_due`，它不需要參數，也不需要 Redis、REST API
   或 frontend。沒有帳單時，收到空的 `data` 或可理解的業務結果即可。
3. 再呼叫 `list_bills` 或 `pipeline_status`，確認 client 讀到的是目標資料庫。

每一個 request 都要等待前一個 response 後再送下一個。stdio 不要用「一次寫完
所有 JSON-RPC request 後立即關閉 stdin」；EOF race 可能只得到
`Connection closed`。

若 HTTP host 連得上但 stdio 顯示 `connected`／tools=6、`tools/call` 卻 `Not
connected`，改連 URL，不要再回收 PID 當主修法。仍走 stdio 時才依
[`mcp-installation.md`](mcp-installation.md) 回收 **stdio** PID（不要殺
`ccas-mcp-http`）。v0.8.2 的 datetime 為 UTC `Z`，不需要 database migration。

如果 tools discovery 失敗，先在 `backend/` 執行 `uv sync --frozen` 並確認 URL
或 command 路徑。若 discovery 成功但資料為空，檢查 `DATABASE_URL`、資料庫檔案
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

### Linux（無 systemd／policy-rc.d）

當 `systemctl` 不存在，或 `systemctl enable --now redis-server` 被 `policy-rc.d`
擋住時，不要改走 Docker，也不要讓 `host-services.sh` 啟動私有 Redis。改用
loopback 上的 `redis-server --daemonize`。`--dir` 不要設成 `/tmp`，否則重開機會
丟掉 RDB：

```bash
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/ccas/redis"
mkdir -p "$STATE"
redis-server --daemonize yes --bind 127.0.0.1 --port 6379 \
  --dir "$STATE" --dbfilename dump.rdb --logfile "$STATE/redis.log"
redis-cli ping
```

預期輸出是 `PONG`。此行程與 supervisord daemon 一樣不會在主機重開機後自動起來。
開機後 checklist：重跑上面的 daemonize →
`./scripts/host-services.sh --driver=supervisord install all` →
`./scripts/host-services.sh --driver=supervisord smoke all`。
可選把 daemonize 與 `host-services.sh ... install all` 放進 `cron @reboot`；
這不是 `host-services.sh` 的自動能力。

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
| `API_TOKEN` 缺少 | 在 backend/ 的 shell export，或寫入本機 `.env`；不要提交 `.env`。HTTP MCP 需要此 token 當 Bearer。 |
| MCP client 顯示 JSON parse error | stdio：stdout 沒有 shell banner 或 debug print。HTTP：確認連的是 `/mcp` 而不是 REST。 |
| tools 顯示 connected 但 call 顯示 `Not connected` | Grok／Cursor 改連 loopback URL。stdio 才走 [`mcp-installation.md`](mcp-installation.md) 的 PID 回收（不要殺 `ccas-mcp-http`）。 |
| `mcp-http is only supported by supervisord` | 改 `--driver=supervisord`，或前景跑 `uv run ccas-mcp-http`。 |
| `pipeline_status` 回 `-32602`／`date-time` | 確認已是 v0.8.2+，走 MCP PID 回收；確認輸出 timestamp 帶 `Z`。 |
| tools 存在但查不到資料 | 確認 `DATABASE_URL`、資料庫檔案權限，以及 client 的 backend 路徑。 |
| worker/scheduler 連不上 queue | 確認 `REDIS_URL`、`redis-cli ping` 與 host service 狀態。 |
| macOS 沒有 `systemctl` | 使用 `brew services` 管理 Homebrew Redis。 |
| Linux `systemctl` 被擋或不存在 | 使用本文件「Linux（無 systemd／policy-rc.d）」的 `redis-server --daemonize`；不要改走 Docker。 |
| Corepack permission denied | 使用 `--install-directory "$HOME/.local/bin"` 並更新 PATH。 |

MCP 的 tools、資料投影與安全邊界仍以 [`mcp-installation.md`](mcp-installation.md)
為準；本文件只補充非 Docker host 的依賴與最小啟動路徑。需要常駐 worker、
scheduler、api 或 `mcp-http` 時，請看 [無 Docker 的 Host Services 維運](non-docker-host-services.md)。
