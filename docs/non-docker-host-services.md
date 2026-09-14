# 無 Docker 的 Host Services 維運

本文件管理不使用 Docker Compose 時的 CCAS background process。範圍包括：

- RQ worker：從 Redis 取出 pipeline job。
- APScheduler：將週期性工作放入 Redis，並寫入 scheduler heartbeat。
- API：只在 supervisord driver 下由本腳本管理。
- Redis：由 Linux 發行版或 macOS Homebrew 提供 host service。

Frontend、Telegram bot 與 MCP server 不由這組 service manager 管理。
MCP-only 的安裝與依賴請看 non-docker-agent-host.md。

## 前置條件

在 repository root 執行：

```bash
cp .env.example .env
cd backend
uv sync --frozen
cd ..
```

.env 必須包含 API_TOKEN，並設定 host Redis：

```dotenv
REDIS_URL=redis://localhost:6379/0
```

Linux 先確認 Redis systemd service 已啟動：

```bash
sudo systemctl enable --now redis-server
redis-cli ping
```

若發行版使用 redis.service，改用該 unit。macOS 使用 Homebrew：

```bash
brew services start redis
redis-cli ping
```

兩個平台的預期輸出都是 PONG。host-services.sh 只做 health check，不會自行
安裝、啟動或監控另一個 Redis instance。

## 安裝與操作

安裝會依下列順序選擇 driver：Linux 先嘗試 systemd user bus，再嘗試專案環境中的
supervisord；macOS 使用 launchd。也可以用 CLI 或環境變數覆寫：CLI 優先於
`CCAS_HOST_SERVICE_DRIVER`。

```bash
./scripts/host-services.sh --driver=supervisord install worker
CCAS_HOST_SERVICE_DRIVER=supervisord ./scripts/host-services.sh status all
```

未指定 driver 時，腳本會把目前 checkout 的絕對路徑與 uv 路徑寫入 user-level
service definition：

```bash
./scripts/host-services.sh install
./scripts/host-services.sh status
./scripts/host-services.sh smoke
```

常用操作：

```bash
./scripts/host-services.sh restart worker
./scripts/host-services.sh restart scheduler
./scripts/host-services.sh status worker
./scripts/host-services.sh uninstall
```

target 可為 `worker`、`scheduler`、`api` 或 `all`。`all` 會依目前 driver 支援的
capabilities 展開；systemd／launchd 不支援 `api`，請使用
`--driver=supervisord`。install 會啟動選定服務，並設定失敗自動重啟：worker/scheduler 在
Linux 使用 Restart=on-failure，在 macOS 使用 KeepAlive=true 與 5 秒 throttle。
執行多次 install 是安全的，會重新產生目前 checkout 的 definition。

## Linux：systemd user services

安裝位置是：

```text
~/.config/systemd/user/ccas-worker.service
~/.config/systemd/user/ccas-scheduler.service
```

檢查詳細狀態與 logs：

```bash
systemctl --user status ccas-worker.service
systemctl --user status ccas-scheduler.service
journalctl --user -u ccas-worker.service -f
journalctl --user -u ccas-scheduler.service -f
```

user service 預設在使用者登入時啟動。若要在未登入時也能於開機後啟動，管理者
可針對目前帳號啟用 linger：

```bash
sudo loginctl enable-linger "$USER"
```

這是主機層級設定，腳本不會自動替使用者開啟。若 SSH session 沒有 user systemd
bus，請在該使用者的正常 login session 執行 install，或先依發行版設定 user bus。

## macOS：launchd LaunchAgents

安裝位置是：

```text
~/Library/LaunchAgents/com.ccas.worker.plist
~/Library/LaunchAgents/com.ccas.scheduler.plist
```

launchd 會在使用者登入時載入兩個 agent；stdout/stderr 會寫入：

```text
~/Library/Logs/ccas-worker.log
~/Library/Logs/ccas-worker.error.log
~/Library/Logs/ccas-scheduler.log
~/Library/Logs/ccas-scheduler.error.log
```

查看 launchd 狀態：

```bash
launchctl print "gui/$(id -u)/com.ccas.worker"
launchctl print "gui/$(id -u)/com.ccas.scheduler"
```

請使用 launchctl 管理這兩個 agent；macOS 沒有 systemd，也不應使用
systemctl --user。

## Linux systemd-less／容器化 host：supervisord

supervisord 是透過 backend optional dependency 安裝的 user-launched daemon，不需
apt、root 或 init system：

```bash
cd backend
uv sync --frozen --extra supervisor
cd ..
./scripts/host-services.sh --driver=supervisord install worker
./scripts/host-services.sh --driver=supervisord install scheduler
./scripts/host-services.sh --driver=supervisord install api
```

設定與狀態檔位於：

```text
${XDG_STATE_HOME:-$HOME/.local/state}/supervisord/supervisord.conf
${XDG_STATE_HOME:-$HOME/.local/state}/supervisord/conf.d/
${XDG_STATE_HOME:-$HOME/.local/state}/supervisord/log/
```

常用操作：

```bash
./scripts/host-services.sh --driver=supervisord status all
./scripts/host-services.sh --driver=supervisord restart api
uv run --directory backend --no-sync supervisorctl \
  -c "$HOME/.local/state/supervisord/supervisord.conf" status
tail -f "$HOME/.local/state/supervisord/log/ccas-api.log"
```

supervisord 會自動重啟它管理的 worker、scheduler 與 API；但它本身不會在主機或
容器 reboot 後自動重新啟動。若需要開機恢復，必須由外部 hook 處理，例如 container
entrypoint、`cron @reboot`，或明確的人工啟動步驟。這不屬於本腳本的自動能力。

## Smoke check 與故障排除

smoke 會依序確認：Redis 回 PONG、選定的 service manager process 存活、RQ
可以連到 queue，以及在選定 scheduler 時 heartbeat 在最近兩分鐘內更新。若選定
`api`，也會以同一個 `/health/ready` endpoint 確認 API 回傳 HTTP 200：

```bash
./scripts/host-services.sh smoke
```

若 smoke 失敗：

1. 先執行 redis-cli ping，確認 host Redis 正在運作且 REDIS_URL 使用正確 port
   與密碼。
2. 查看 worker/scheduler 的 service logs。
3. 若包含 api，查看 supervisord API log，並以 curl 檢查
   `http://127.0.0.1:8000/health/ready`。
4. 確認 API_TOKEN、DATABASE_URL、REDIS_URL 在 repository root .env，並且
   執行 uv sync --frozen 後再重試。
5. 確認 backend/data/scheduler-heartbeat 可寫入；若設定了
   SCHEDULER_HEARTBEAT_PATH，改檢查該路徑。

若只要暫停背景服務，使用 uninstall；這不會刪除 SQLite、staging、Redis 資料或
.env。
