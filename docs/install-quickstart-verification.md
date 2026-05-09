# Install Quickstart 端對端驗證 Runbook

本文件為 `compose-pull-deploy` change 的 §6 端對端驗證清單，於 PR 合入 master、
release-docker workflow 推送 `v0.1.0-rc.1` image 至 GHCR 後，**release manager
依本清單跑一輪驗證**。所有項目通過才能升正式 `v0.1.0` tag。

> 本 runbook 中提到的 `${CCAS_PORT}` / `${CCAS_DATA_LOCATION}` 等變數，請以你 `.env`
> 中的實際值替換；下列範例使用預設 `8080` / `./data`。

## 目前本機預驗證紀錄

2026-05-09 以本機 production image 預驗證，不取代 release manager 的 GHCR
`v0.1.0-rc.1` sign-off：

- 工作目錄：`/tmp/ccas-openspec-verify`
- 映像：`ghcr.io/hmj1026/ccas-backend:local`、`ccas-frontend:local`、`ccas-proxy:local`
- `.env`：`CCAS_VERSION=local`、`CCAS_PORT=12284`、`PUBLIC_BASE_URL=http://localhost:12284`
- 通過：`/api/health` 200、`data/secrets/{api-token,api-token-version,master.key}` 自動建立且 0600、首次登入 `/login` → `/overview`
- 通過：`/setup/secrets` env-only 橫幅顯示 7 筆，點「一鍵匯入 env 密碼」後 7 筆皆轉為 DB source，env fallback 仍可見，SQLite 中 ciphertext 不含 env 明文
- 通過：`/setup/gmail` 顯示 `http://localhost:12284/setup/gmail/callback`，上傳 `credentials.json` 後 authorize URL 使用同一 redirect URI 與 PKCE S256
- 通過：`/tmp/ccas-telegram-verify` 以同一份 `.env` 補入 Telegram 變數、`CCAS_VERSION=local`、`CCAS_PORT=12285`，不使用 `--profile`；bot service `healthy`、Telegram `getMe.ok=true`、`sendMessage.ok=true`，proxy `/api/health` 200（token/chat id 未寫入紀錄）

仍需 release / 外部服務驗證：GHCR 假 tag workflow、真實 Google OAuth
consent / callback / revoke、`v0.1.0-rc.1` → `v0.1.0-rc.2` 升級、多架構 pull、
正式 tag 與 archive。

---

## 環境準備

```bash
mkdir /tmp/ccas-fresh && cd /tmp/ccas-fresh
RELEASE=v0.1.0-rc.1
curl -fsSL -o docker-compose.yml \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/docker-compose.yml"
curl -fsSL -o example.env \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/example.env"
cp example.env .env
# 編輯 .env 填入 REPO_OWNER、CCAS_VERSION、PDF_PASSWORD_*、Telegram（如測試）
mkdir -p data && cp ~/secure-place/credentials.json data/credentials.json
```

---

## §6.1 — 基本啟動

```bash
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
docker compose ps
```

**通過條件**：所有 service 進入 `Up` 或 `Up (healthy)`。

## §6.2 — 服務健康檢查

```bash
curl -fsS "http://localhost:${CCAS_PORT:-8080}/api/health"
docker compose logs redis | grep -i ready
docker compose logs worker | grep -iE "rq|listening"
docker compose logs scheduler | grep -i started
```

**通過條件**：backend `/api/health` 回 200；redis ready；worker listening；scheduler started。

## §6.3 — Proxy 可訪問 + 內部 port 不對外

```bash
curl -fsS "http://localhost:${CCAS_PORT:-8080}"        # 200 frontend SPA
curl -fsS "http://localhost:${CCAS_PORT:-8080}/api/health"   # 200 backend API
curl --max-time 2 http://localhost:8000/health 2>&1 || echo "EXPECTED: connection refused"
curl --max-time 2 http://localhost:8080  # 若 CCAS_PORT 不是 8080，此命令應拒絕
```

**通過條件**：proxy port 兩條 route 都通；backend 8000 直連被拒；frontend internal port 不對 host 開。

## §6.4 — Telegram bot 啟用

`.env` 填入測試用 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 後 `up -d`：

```bash
docker compose logs bot | grep -iE "started|connected"
# 從 Telegram 對 bot 發 /start，應收到回覆
```

**通過條件**：bot 自動啟動（無 `--profile`）；可雙向通訊。

## §6.5 — 升級測試

```bash
sed -i.bak 's/CCAS_VERSION=v0.1.0-rc.1/CCAS_VERSION=v0.1.0-rc.2/' .env
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
docker compose logs backend | grep -i alembic
sqlite3 data/ccas.db "SELECT count(*) FROM transactions;"
```

**通過條件**：alembic migration 自動執行、無錯；既有 transaction 數量保留。

## §6.6 — Multi-arch（M 系列 Mac）

於 Apple Silicon 機器執行 §6.1 全套，並驗證：

```bash
docker inspect ghcr.io/${REPO_OWNER}/ccas-backend:${CCAS_VERSION} \
  --format '{{.Architecture}}'    # 應為 arm64
```

**通過條件**：`linux/arm64` variant 拉取啟動成功。

## §6.7 — 異常路徑（缺必填變數）

```bash
sed -i.bak 's/^GMAIL_CREDENTIALS_PATH=.*//' .env
docker compose -f docker-compose.yml up -d
docker compose logs backend | grep -i "缺少必要環境變數"
```

**通過條件**：backend 啟動 fail-fast、log 明示哪個變數缺。

## §6.8 — Config seed 自動觸發

```bash
rm config/banks.yaml   # 模擬使用者誤刪
docker compose -f docker-compose.yml restart backend
docker compose logs backend | grep -i "已從 image 範本複製預設值"
test -f config/banks.yaml && echo "RESEEDED OK"
```

**通過條件**：entrypoint 偵測缺檔、從 image 內建範本複製、log WARN。

## §6.9 — Telegram disabled

```bash
sed -i.bak 's/^TELEGRAM_BOT_TOKEN=.*/# TELEGRAM_BOT_TOKEN=/' .env
docker compose -f docker-compose.yml up -d
docker compose ps bot       # 應顯示 healthy（idle 模式）
curl -fsS "http://localhost:${CCAS_PORT}/api/health"   # backend 不受影響
```

**通過條件**：bot service 不 crashloop；backend 仍 200；logs 顯示 disabled。

## §6.10 — API_TOKEN 自動產生

```bash
sed -i.bak 's/^API_TOKEN=.*/# API_TOKEN=/' .env
rm -rf data/secrets
docker compose -f docker-compose.yml up -d
docker compose logs backend | grep "已自動產生 API_TOKEN"
ls -l data/secrets/api-token       # 權限應為 -rw-------（0600）
TOKEN=$(cat data/secrets/api-token)
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:${CCAS_PORT}/api/auth/whoami"

# 冪等性：重啟後 token 不變
docker compose restart backend
NEW_TOKEN=$(cat data/secrets/api-token)
[ "$TOKEN" = "$NEW_TOKEN" ] && echo "TOKEN STABLE OK"
```

**通過條件**：(a) INFO log 出現；(b) token 檔權限 0600；(c) token 可呼叫受保護 API；(d) 重啟後 token 不變。

## §6.11 — 單一外部入口

```bash
curl -fsS "http://localhost:${CCAS_PORT:-8080}/api/health"   # 200
curl --max-time 2 http://localhost:8000/health 2>&1 || echo "OK: refused"
curl --max-time 2 http://localhost:6379 2>&1 || echo "OK: refused"
```

**通過條件**：只有 `${CCAS_PORT}` 對外；backend 8000 / redis 6379 / frontend internal 拒絕。

## §6.12 — 備份 / 還原

```bash
docker compose down
tar -czf /tmp/ccas-backup.tar.gz data/

# 在另一目錄還原
mkdir /tmp/ccas-restore && cd /tmp/ccas-restore
cp /tmp/ccas-fresh/docker-compose.yml .
cp /tmp/ccas-fresh/.env .
tar -xzf /tmp/ccas-backup.tar.gz
docker compose up -d
curl -fsS "http://localhost:${CCAS_PORT}/api/health"
sqlite3 data/ccas.db "SELECT count(*) FROM transactions;"
```

**通過條件**：服務正常啟動、SQLite / staging / token 全保留、用同一 token 仍可登入。

## §6.13 — Proxy headers 驗證

```bash
curl -v "http://localhost:${CCAS_PORT}/api/health"
docker compose logs backend --tail 50 | grep -E "client_addr|X-Forwarded"

# Cookie 持久化
curl -c cookies.txt -b cookies.txt -X POST \
  -H "Content-Type: application/json" \
  -d '{"token":"<api-token>"}' \
  "http://localhost:${CCAS_PORT}/api/auth/login"
curl -b cookies.txt "http://localhost:${CCAS_PORT}/api/auth/whoami"

# Upgrade header（為 SSE / WebSocket 預留）
curl -v -H "Connection: Upgrade" -H "Upgrade: websocket" \
  "http://localhost:${CCAS_PORT}/api/health" 2>&1 | grep -i upgrade
```

**通過條件**：backend 看到實際 host IP（非 127.0.0.1）；cookie 持久；nginx 不剝 Upgrade header。

## §6.14 — 首次登入 UX

依 [install-quickstart.md](install-quickstart.md) 步驟 6 操作，全程不開 terminal
觀察 backend log、不執行其他 docker 指令：

1. `cat data/secrets/api-token` → 取得 token（這是 quickstart 文件指引的指令）
2. 瀏覽器開 `http://localhost:${CCAS_PORT}/login`
3. 貼上 token 送出
4. 進入 dashboard

**通過條件**：30 秒內完成、無需 backend log 排錯。

## §6.15 — `CCAS_PORT` 自訂

```bash
sed -i.bak 's/^CCAS_PORT=.*/CCAS_PORT=12283/' .env
docker compose -f docker-compose.yml up -d   # 不 rebuild
curl -fsS "http://localhost:12283/api/health"

# Frontend bundle 內無絕對 backend URL（仰賴同源 proxy）
docker run --rm $(docker images -q "ghcr.io/${REPO_OWNER}/ccas-frontend:${CCAS_VERSION}") \
  sh -c 'grep -rE "localhost:8000|backend:8000" /usr/share/nginx/html' \
  || echo "OK: bundle has no absolute backend URL"
```

**通過條件**：12283 完整服務正常；frontend image digest 未變、bundle 不含絕對 URL。

---

## §7 release sign-off

§6 全綠後：

1. **§7.2** 驗證外部 user `docker pull ghcr.io/${REPO_OWNER}/ccas-backend:v0.1.0-rc.1` 成功（GHCR public 切換完成）
2. **§7.3** GHCR package settings 切換為 public（首次 release 後 manual）
3. **§7.4** 在 §6.1–§6.15 裡釘 `CCAS_VERSION=v0.1.0-rc.1` 重跑一輪
4. **§7.5** 推 `v0.1.0` 正式 tag、release-docker workflow 自動建立 release page；README 連結指向 release asset URL
5. **§7.6** 執行 `/opsx:archive compose-pull-deploy` 將 delta spec 同步至 `openspec/specs/`

---

## §6 / §7 不能在合 PR 前執行的原因

- §6 全部需要 GHCR 上有 release image（PR 合入 master + release workflow 跑完才會有）
- §7 為 release event 本身（推 tag、archive change）

故本 PR（PR-A4 docs）僅勾選 §5 docs 任務；§6 / §7 待 PR-A1~A4 全合入後依本 runbook 執行。
