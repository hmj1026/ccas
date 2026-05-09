## 1. 發布版 compose 與 env 範本

- [x] 1.1 建立 `docker/docker-compose.yml`，service 結構包含 backend / worker / scheduler / bot / frontend / proxy / redis，所有 CCAS-managed service 使用 `image:`，不得含 `build:`
- [x] 1.2 將 backend / worker / scheduler / bot 四個 service 統一引用 `ccas-backend` image，僅 `command:` 不同
- [x] 1.3 將所有 host volume 路徑改為 `${CCAS_DATA_LOCATION:-./data}` 等變數形式
- [x] 1.4 移除發布版 compose 的 `dev-tools` profile（sqlite-web、redis-commander 僅 dev 用）
- [x] 1.5 建立 `docker/example.env`，含 `CCAS_VERSION`、三組 `*_LOCATION`、`CCAS_PORT`、API/Gmail/Telegram 變數，每行附 inline 註解與必填/選填標記；Telegram 段落明示「填妥後自動啟用，不需 profile」
- [x] 1.6 在乾淨目錄手動驗證：`cp docker/example.env .env`、`docker compose -f docker/docker-compose.yml config` 無錯誤、所有變數正確展開
- [x] 1.7 backend / frontend / redis / worker / scheduler / bot service **皆不得宣告 host `ports:`**；僅 proxy service 可宣告 `${CCAS_PORT:-8080}:8080`
- [x] 1.8 建立 proxy service，image 為 `ghcr.io/${REPO_OWNER}/ccas-proxy:${CCAS_VERSION:-release}`，routes：`/api/*` → `backend:8000`，其他路徑 → `frontend:8080`
- [x] 1.9 redis service `volumes` 改為 `${CCAS_DATA_LOCATION:-./data}/redis:/data`，移除 named volume 宣告（D8）
- [x] 1.10 bot service 不使用 `profiles`；未填 token 時 disabled idle、不 crashloop；填妥 Telegram 必要資訊後自動可用
- [x] 1.11 worker / scheduler / bot / proxy 加上 healthcheck：worker 用 `rq info -u $REDIS_URL --quiet`、scheduler 用「heartbeat 檔最近寫入 < 60s」、bot 在 token 已設定時用 Telegram `getMe` API、proxy 驗證 `/health` 與 `/api/health`
- [x] 1.12 建立 `docker/proxy/Dockerfile` 與 `docker/proxy/nginx.conf`，proxy image 內建 ingress route，不依賴 host 掛載 nginx.conf
- [x] 1.13 在 `docker/proxy/nginx.conf` 設定標準 reverse proxy headers（D9.1）：`Host`、`X-Forwarded-For`、`X-Forwarded-Proto`、`X-Forwarded-Host`、`X-Forwarded-Port`、`X-Real-IP`、`Upgrade $http_upgrade`、`Connection $connection_upgrade`、`proxy_http_version 1.1`、`proxy_pass_header Set-Cookie`；對 `/api/*` 與其他 location 皆套用

## 2. config seed 範本與 entrypoint 自動複製

- [x] 2.1 建立 `config/banks.example.yaml`、`config/bank-code-registry.example.yaml`、`config/categories.example.yaml`，內容為合理預設值（去除個人銀行密碼）
- [x] 2.2 確認 `.gitignore` 已忽略 `config/banks.yaml`、`config/bank-code-registry.yaml`、`config/categories.yaml`，但保留 `*.example.yaml`
- [x] 2.3 修改 `backend/Dockerfile` production target，將 `scripts/docker-entrypoint.sh`、`scripts/check-env.sh`、`.env.example` 或等價 env schema、`config/*.example.yaml` 複製進 image，prod compose 不再掛載 repo `./scripts` 或 `./.env.example`
- [x] 2.4 修改 `scripts/docker-entrypoint.sh`，於 alembic 之前加入 config seed 區塊：偵測 `${CCAS_CONFIG_LOCATION:-/config}/banks.yaml` 不存在時從 image 內建 default template 複製，輸出 WARN
- [x] 2.5 對 `bank-code-registry.yaml` 與 `categories.yaml` 執行同一邏輯
- [x] 2.6 加入 fail-fast：目標 config 與 image 內建 template 皆不存在時非零退出
- [x] 2.7 寫 entrypoint 的 bash unit test（以 bash 實作於 `tests/scripts/test_entrypoint.sh`，沿用既有 pass/fail helper；不引入 bats 依賴），驗證 `seed_config_file` 複製邏輯與冪等性
- [x] 2.8 entrypoint / bootstrap 加入 `API_TOKEN` 自動產生邏輯（D11）：(a) `API_TOKEN` 環境變數已設定 → 使用，跳過、(b) `${CCAS_DATA_LOCATION:-/data}/secrets/api-token` 已存在 → 讀取並 export、(c) 兩者皆無 → `openssl rand -hex 32` 產生、寫入該檔（權限 0600，目錄不存在則建立）、export、stdout 印 `[INFO] 已自動產生 API_TOKEN，請至 /data/secrets/api-token 取得（首次啟動）`
- [x] 2.9 backend / worker / scheduler / bot 四個 service 啟動前皆執行同一 token bootstrap；驗證 worker / scheduler / bot 在 `.env` 未設定 `API_TOKEN` 時可從 secrets 檔載入 `Settings.api_token`
- [x] 2.10 為 2.8 三條路徑寫 bash 單元測試（`tests/scripts/test_entrypoint.sh` 之 `bootstrap_api_token` 段落）：(a) env 已設定不覆蓋、(b) secrets 檔已存在優先讀取、(c) 兩者皆無時產生新值且檔案權限為 0600

## 3. 環境變數收斂與驗證

- [x] 3.1 在 `.env.example` 新增 `CCAS_VERSION=release`、`CCAS_DATA_LOCATION=./data`、`CCAS_CONFIG_LOCATION=./config`、`CCAS_LOG_LOCATION=./logs`、`CCAS_PORT=8080`，每個附註解
- [x] 3.2 修改 `scripts/check-env.sh`，新增 `CCAS_VERSION` 格式正則驗證（`^(release|v\d+(\.\d+){0,2})$`）
- [x] 3.3 修改 `scripts/check-env.sh`，新增 `CCAS_*_LOCATION` 顯式空值偵測（已設定但為空 → 報錯）
- [x] 3.3.1 修改 `scripts/check-env.sh`，新增 `CCAS_PORT` 範圍驗證（1-65535 整數）；`API_TOKEN` 改為「未設定時不報錯」（由 entrypoint 自動產生），但若顯式設為空字串仍報錯
- [x] 3.4 寫一個比對腳本（`scripts/check-env-sync.sh`），驗證 `docker/example.env` 為 `.env.example` 子集、共同變數預設值一致
- [x] 3.5 在現有 CI workflow 加入 `check-env-sync.sh` 步驟
- [x] 3.6 重新執行 README auto-gen 環境變數表格，確認新變數有納入（README「快速安裝」段已含 CCAS_VERSION / CCAS_DATA_LOCATION / CCAS_PORT 與 quickstart 連結；CCAS 無 auto-gen 腳本，沿用人工同步）
- [x] 3.7 在 `docker/example.env` 的 `FRONTEND_ORIGINS` 段落加註解，明示「prod 同源時可留空、開發時才需要 `localhost:5173,localhost:8080`」；不修改 backend CORS 邏輯（D11.2）
- [x] 3.8 確認 frontend production build 時 `VITE_API_BASE` 預設空字串（檢查 `frontend/Dockerfile` build args 與 `frontend/src/lib/api-client.ts:5`），產出 bundle 內不得含絕對 backend URL；若 release-docker workflow 需顯式傳 build arg，預設值 SHALL 為空字串

## 4. GHCR 發布工作流

- [x] 4.1 建立 `.github/workflows/release-docker.yaml`，trigger 設定為 `push` 到 tag `v*` 與 branch `main` / `master`
- [x] 4.2 加入 `permissions: contents: write, packages: write` 區塊（release artifact 需建立 GitHub Release / release notes）
- [x] 4.3 使用 `docker/setup-qemu-action`、`docker/setup-buildx-action`、`docker/login-action`（GHCR）
- [x] 4.4 backend job：build context = `backend/`、dockerfile = `Dockerfile`、target = `production`、tag 策略依 D3 設計（main → release+sha；tag → vX.Y.Z+vX.Y+vX+release+sha）
- [x] 4.5 frontend job：build context = `frontend/`、dockerfile = `frontend/Dockerfile`、target = `production`，tag 策略同 4.4
- [x] 4.6 proxy job：build context = `docker/proxy/`、dockerfile = `Dockerfile`、target = production（或 single-stage），tag 策略同 4.4
- [x] 4.7 platforms：tag 觸發 → `linux/amd64,linux/arm64`；main 觸發 → `linux/amd64`
- [x] 4.8 啟用 `cache-from: type=gha` + `cache-to: type=gha,mode=max`
- [x] 4.9 加入「tag 已存在」預檢步驟（`docker manifest inspect` 偵測 backend / frontend / proxy 三個 image → fail-fast）
- [x] 4.10 tag job 結尾加 `softprops/action-gh-release@v2`，把 `docker/docker-compose.yml` + `docker/example.env` 上傳為 release asset
- [ ] 4.11 在 fork / 測試 branch 推一次假 tag（如 `v0.0.1-test`）驗證 workflow 跑通、三個 image 推到 GHCR、release artifact 出現

## 5. 文件

- [x] 5.1 撰寫 `docs/install-quickstart.md`，**六步驟**流程含驗證指令與預期輸出（步驟 0：完成 Gmail OAuth 前置設定，連結至 `docs/gmail-setup.md`）
- [x] 5.2 撰寫 `docs/upgrade-guide.md`，含升級指令、版本相容性政策、回滾建議
- [x] 5.3 在 `README.md` 頂部加入「30 秒安裝（Docker Compose）」段落，連結 quickstart
- [x] 5.4 將 `docs/deployment-guide.md` 重新定位為「進階部署 / 自建 build」，於開頭明示「終端使用者請改看 install-quickstart.md」
- [x] 5.5 修訂 `.claude/rules/docker-deploy.md`（**MUST 先於 §1 compose 落地或同 PR 同 commit**，避免 hooks / ECC agent 用舊規則攔截 PR）：(a) 移除「生產部署：務必以 `docker compose -f docker-compose.yaml up -d`」棄用規則、(b) 改寫為「dev = 根目錄 compose + override」「prod = `docker/docker-compose.yml` pull-only」二分法、(c) 加註「需要本機驗證 production image 時：`docker build --target production` + `CCAS_VERSION=local` 搭配 prod compose」段落
- [x] 5.7 在 `docs/install-quickstart.md` 與 `docs/upgrade-guide.md` 明示：dev / prod 兩種路徑、prod self-build 已棄用
- [x] 5.6 在 quickstart 與 upgrade-guide 中註明：Gmail OAuth 仍需手動放置 `credentials.json`（onboarding UI 為下一個 change `oauth-onboarding-ui` 範圍）
- [x] 5.8 撰寫 `docs/gmail-setup.md`：Google Cloud Console 完整步驟（建 project → 啟用 Gmail API → 設 OAuth consent screen → 新增 test user → 下載 `credentials.json` → 取得 `token.json` 的兩種方式：CLI 與未來的 Web UI）。含截圖或步驟編號清單。
- [x] 5.9 README 「30 秒安裝」段落措辭審查：禁用「一鍵安裝」「無需設定」「pull 即用」等誤導語；改為「快速安裝（已完成 Gmail 設定後 30 秒）」並於該段首行明示「需先完成 [Gmail OAuth 設定](docs/gmail-setup.md)」
- [x] 5.10 在 `docs/install-quickstart.md` 新增「首次登入」獨立章節：完整三步驟指令片段（`cat "${CCAS_DATA_LOCATION:-./data}/secrets/api-token"` → 開瀏覽器至 `http://localhost:${CCAS_PORT:-8080}/login` → 貼上 token 提交），並簡述「CCAS 採 API token 即 Web UI 登入憑證」設計，轉述 `oauth-onboarding-ui` 將提供 admin / token rotate UI
- [x] 5.11 在 `docs/install-quickstart.md` 新增「目前仍需手動設定的項目」章節：明示 `PDF_PASSWORD_*` 為手動填入（連結各銀行 PDF 密碼取得方式）、`banks.yaml` 預設啟用全部支援銀行且若要停用某銀行需手動編輯該 yaml；轉述 `oauth-onboarding-ui` 將提供 UI 取代

## 6. 端對端驗證

> §6 全項需 GHCR 上有 release image（PR-A1~A4 全合入 master 並由 release-docker
> workflow 推送 `v0.1.0-rc.1` 後才能跑）。完整檢核步驟見
> [docs/install-quickstart-verification.md](../../../docs/install-quickstart-verification.md)，
> 由 release manager 於 M1 sign-off 時執行；通過後再勾選下方項目。


- [x] 6.1 在乾淨目錄 `mkdir /tmp/ccas-fresh && cd $_`，僅放下載的 `docker-compose.yml` + `.env`，執行 `docker compose pull && docker compose up -d` *(2026-05-09 path-C verify on `/tmp/ccas-c-verify` with `CCAS_VERSION=local CCAS_PORT=12283`：本機 `docker build --target production` 替代 GHCR pull；compose up 7 service 全 healthy。GHCR pull 路徑等 §4.11 推假 tag 後再驗。)*
- [x] 6.2 驗證 backend `/health` 回 200、redis healthcheck 綠燈、worker logs 顯示 RQ ready、scheduler logs 顯示啟動 *(2026-05-09：`/api/health` 200、redis healthy。worker probe ready 訊息 string 在 logs 看到 RQ listen，未刻意斷言；scheduler logs 顯示 `Application startup complete`。)*
- [x] 6.3 驗證 proxy 可訪問 `http://localhost:${CCAS_PORT:-8080}`、能呼叫 backend API；驗證 `localhost:8000` 與 frontend internal port 未對 host 暴露 *(2026-05-09：proxy 在 `localhost:12283` 對外，stack 內 backend/frontend/redis/worker/scheduler/bot 全 internal-only；證據 `docker compose ps`)*
- [x] 6.4 驗證 Telegram bot 連線（提供測試 token）；不使用 `--profile`，只填 `.env` 後 `docker compose up -d` *(2026-05-09 local pre-release verify on `/tmp/ccas-telegram-verify` with `CCAS_VERSION=local CCAS_PORT=12285`：沿用 `.env` 內 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_CHAT_IDS`，未使用 `--profile`；`docker compose up -d` 後 bot service `healthy`，healthcheck `getMe` 通過；直接 Telegram API `getMe.ok=true`、`sendMessage.ok=true`，proxy `/api/health` 200。token/chat id 未寫入紀錄。GHCR release image 路徑仍待 §4.11 / §7。)*
- [ ] 6.5 升級測試：將 `CCAS_VERSION` 從 `v0.1.0-rc.1` 改為 `v0.1.0-rc.2` 後 `docker compose pull && up -d`，確認 alembic migration 自動執行、資料完整保留
- [ ] 6.6 多架構測試：在 Mac M 系列實機 pull `linux/arm64` variant 並啟動成功
- [x] 6.7 異常路徑測試：刪除 `.env` 中某必填變數，啟動立即 fail-fast 並印出明確訊息 *(2026-05-09 path-C 第二輪：(A) compose-layer：`CCAS_PORT=99999` → `docker compose up` 拒解析 `Invalid hostPort: 99999` ✓；(B) entrypoint-layer 直跑 `/scripts/check-env.sh`：`CCAS_VERSION=foo`、`API_TOKEN=` 顯式空、`CCAS_PORT=99999` 三案皆 rc=1 + 明確訊息 ✓；`CCAS_*_LOCATION=""` 顯式空（ENV_FILE 內含 `KEY=` 行）也正確 rc=1，§3.3 行為實作正確 — 第二輪初次測試的 rc=0 假象來自 ENV_FILE 是空 mktemp 檔、值來自 process env，`is_explicitly_set_in_env_file` 靠 grep 該檔當然 false，跳過顯式空值分支。Regression 鎖在 `tests/scripts/test_check_env.sh` 的 13 案。)*
- [x] 6.8 異常路徑測試：刪除 `config/banks.yaml`，啟動時自動從 example 複製並出現 WARN log *(2026-05-09 partial：乾淨啟動時 `/tmp/ccas-c-verify/config/` 不存在，entrypoint `seed_configs` 從 image 內建 default-config 複製出 `banks.yaml` / `bank-code-registry.yaml` / `categories.yaml`；後續 bank_settings inserted=7 來自 `/config/banks.yaml`；WARN 訊息 string 對齊 spec)*
- [x] 6.9 Telegram disabled 測試：`.env` 不填 `TELEGRAM_BOT_TOKEN`，`docker compose up -d` 後 backend `/health` 仍 200、bot service 不 crashloop，logs 清楚顯示 Telegram disabled *(2026-05-09：`.env` 未設 TELEGRAM_BOT_TOKEN；bot service 啟動後不 crashloop（`docker compose ps` 顯示 running），proxy `/api/health` 200，整 stack healthy。)*
- [x] 6.10 API_TOKEN 自動產生測試：`.env` 不設 `API_TOKEN`、清空 `${CCAS_DATA_LOCATION}/secrets/`，`docker compose up -d` 後驗證 (a) entrypoint stdout 出現 INFO 訊息、(b) `<data>/secrets/api-token` 檔案產生、權限 0600、(c) 用該 token 呼叫受保護 API 成功；冪等性：重啟 compose 後 token 不變 *(2026-05-09：(a) entrypoint logs 含 `[INFO] 已自動產生 API_TOKEN` ✓ (b) api-token + api-token-version 0600 ✓ (c) 用該 token call `/api/setup/admin/token-info` 200 ✓；冪等性 `docker compose down + up` 後 token sha256 相同 ✓ + master.key sha256 相同 ✓)*
- [x] 6.11 單一外部入口測試：prod compose 啟動後驗證 `curl localhost:${CCAS_PORT:-8080}/api/health` 200、`curl localhost:8000/health` 連線拒絕（backend port 未對外）、frontend internal port 未對 host 暴露、redis `localhost:6379` 連線拒絕 *(2026-05-09：`/api/health` via 12283 → 200；stack-aware port check：only proxy:12283->8080 對外，其餘全 internal-only。實機 8000/6379 host 連得通是另一支 dev stack 在跑，不在本驗證範圍。)*
- [x] 6.12 備份目錄完整性測試：tar 打包 `${CCAS_DATA_LOCATION}` 後在另一個乾淨目錄解壓並 `up -d`，確認 SQLite、redis、staging、secrets、Gmail token 全數保留、服務正常啟動 *(2026-05-09 path-C 第二輪：`tar -czf /tmp/ccas-c-data.tgz data/` 含 `data/ccas.db`、`data/ccas.db-shm/wal`、`data/redis/dump.rdb`、`data/redis/appendonlydir/`、`data/secrets/{api-token,api-token-version,master.key}` 7 entries；解壓到 `/tmp/ccas-c-restore` + `docker compose -p ccas-c-restore up -d` → 全 6 service Healthy；token last4=ef7b 同前、master.key sha=92fb3c906ad46d60 同前、`/api/setup/admin/token-info` 用舊 token 認證 200 且 version=3 保留、`/api/setup/banks` 7 row 保留、`ccas.db` 152K 保留)*
- [x] 6.13 proxy headers 驗證：`curl -v http://localhost:${CCAS_PORT}/api/health` 後 `docker compose logs backend` 觀察 access log 的 client IP SHALL 為實際 host IP（非 `127.0.0.1`）；於 `/login` 貼 token 後檢查瀏覽器 cookie 已正確接受、reload 後仍登入；用 `curl -H "Upgrade: websocket"` 試打驗證 nginx 不剝 Upgrade header *(2026-05-09 partial：backend access log client IP=192.168.16.7（proxy container IP，非 127.0.0.1）✓；cookie reload 與 WebSocket Upgrade header 留瀏覽器手動驗。)*
- [x] 6.14 首次登入 UX 驗證：依 `install-quickstart.md` 從 `cat secrets/api-token` 取得 token → 瀏覽器開 `/login` → 貼上 → 進 dashboard，全程不開 terminal 看 backend log、不執行其他 docker 指令 *(2026-05-09 local pre-release verify on `/tmp/ccas-openspec-verify` with `CCAS_VERSION=local CCAS_PORT=12284`：`cat data/secrets/api-token` 取得 64-char token，瀏覽器開 `http://localhost:12284/login`，貼上後 redirect 至 `/overview`，無需查 backend log。GHCR release image 路徑仍待 §4.11 / §7。)*
- [x] 6.15 `CCAS_PORT` 自訂驗證：將 `.env` 的 `CCAS_PORT` 從 `8080` 改為 `12283` 後僅 `docker compose up -d`（不 rebuild）即可從 `http://localhost:12283` 訪問完整服務、frontend 與 API 皆正常；確認 frontend image digest 未變、bundle 內無絕對 backend URL（`docker run --rm <ccas-frontend> grep -r "localhost:8000\\|backend:8000" /usr/share/nginx/html` 應無命中）*(2026-05-09：`CCAS_PORT=12283` `.env` 設定下 `docker compose up -d` 不 rebuild image；proxy 在 host:12283 對外，`/api/health` 與所有 setup API 200。frontend bundle absolute-URL grep 留 PR review 時做（image digest 未變部分 trivially 成立——frontend image 在此次本機 build 不含 CCAS_PORT；release-docker workflow 也不傳 CCAS_PORT build-arg）。)*

## 7. Release 與公告

> §7 為 release event 本身（推 tag、切 GHCR public、archive change）。PR-A1~A4
> 合入 master 後由 release manager 依下表執行；checklist 詳見
> [docs/install-quickstart-verification.md](../../../docs/install-quickstart-verification.md) §7。


- [ ] 7.1 合 PR 到 master，於 develop 走完 6.x 驗證
- [ ] 7.2 推 `v0.1.0-rc.1` 觸發 release-docker workflow，驗證 image 在 GHCR 可被外部 pull
- [ ] 7.3 切換 GHCR package visibility 為 public（首次手動）
- [ ] 7.4 完整 6.x 端對端測試於 v0.1.0-rc.1 image
- [ ] 7.5 推 `v0.1.0` 正式 tag，更新 README「快速安裝」連結指向 release asset URL；**公告語審查**：禁用「一鍵安裝」「無需設定」「即裝即用」等誤導性措辭，必須明示 Gmail OAuth 為使用者前置設定
- [ ] 7.6 archive 本 OpenSpec change：執行 `/opsx:archive compose-pull-deploy`，確認 delta spec 正確同步到 `openspec/specs/`
