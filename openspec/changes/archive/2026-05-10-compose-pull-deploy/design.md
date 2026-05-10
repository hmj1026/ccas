## Context

CCAS 是個多進程 pipeline（FastAPI、worker、scheduler、Telegram bot、frontend、redis），目前的 `docker-compose.yaml` 在每個服務節點都帶 `build:` 區塊，假設使用者持有完整原始碼。終端使用者要在新機器跑起來，必須先 `git clone`、再執行 `docker compose build`，build context 約 200MB+，首次啟動數分鐘。

immich 的安裝體驗（單一 `docker-compose.yml` + `example.env`，下載即跑、`docker compose pull && up -d`）來自三個基礎決策：image 由 GHCR 集中發布、compose 檔不依賴本地原始碼、版本透過單一環境變數 pin。本 change 把這三個決策套用到 CCAS。

現況限制：
- 沒有 image registry。CI 只跑 lint/test，從未 docker build。
- 無 release tagging 慣例（`develop` / `master` 直接 push、無 git tag）。
- `config/banks.yaml` 等 seed 檔沒有 example，新環境第一次啟動 entrypoint 會 fail。
- `.env.example` 沒有 image 版本欄位、volume 路徑寫死在 compose（`./backend/data:/data`）。

## Goals / Non-Goals

**Goals:**
- 終端使用者僅需 `docker-compose.yml` + `.env` 兩份檔案，執行 `docker compose pull && docker compose up -d` 即啟動 backend、worker、scheduler、bot、frontend、redis。
- 升級流程為單行 `docker compose pull && docker compose up -d`，alembic migration 自動執行、不需手動。
- 既有開發者用 `docker-compose.yaml`（dev 模式含 `build:` + override）的工作流完全不變。
- 多架構 image（amd64 + arm64）支援 Mac M 系列實機。
- 版本一致：`.env` 的 `CCAS_VERSION=v0.1.0` 同時 pin backend 與 frontend image tag，避免版本錯位。

**Non-Goals:**
- Gmail OAuth onboarding 前端化（拆給 `oauth-onboarding-ui`）。
- Docker Hub 第二發布站（GHCR only）。
- Docker secrets `_FILE` 模式（後續 enhancement）。
- 由 SQLite 切換到 PostgreSQL（與本 change 正交，獨立決策）。
- 雲端託管（AWS / GCP terraform）— 範疇限於本機 docker host。

## Decisions

### D1：compose 檔分流為兩份，而非用單一檔加 profile 切換

選擇：`docker-compose.yaml`（dev，含 `build:`）+ `docker/docker-compose.yml`（prod，純 `image:`）。

替代方案考慮：
- **單檔 + profile 切換**：在同一檔用 `build:` 與 `image:` 並存，prod 加 profile 排除 build。被否決：compose 不允許同 service 同時宣告 build 與 image 而不指定 default 行為，且雙重定義會混淆 review。
- **單檔純 image**：把 build 從 dev compose 移除、由 `docker-compose.override.yml` 補回 build。被否決：override 機制原意是 dev 額外加東西，倒過來在 dev 補 build 反直覺，新貢獻者容易踩坑。

理由：immich 自身就是 `docker/docker-compose.yml` 為發布版、根目錄 dev compose 為開發版的分流，慣例成熟、可直接借鑒。dev compose 完全不動 → 保證既有 PR 不衝突。

**附帶決策**：同步收斂啟動路徑為兩種，**棄用「prod self-build」中間路徑**（先前 `docker-deploy.md` 規範的 `docker compose -f docker-compose.yaml up -d`）。

| # | 路徑 | 對象 | 啟動 |
|---|---|---|---|
| 1 | dev | 開發者 | `docker compose up`（根目錄 + override 自動載入）|
| 2 | prod pull | 終端使用者 | `docker compose -f docker/docker-compose.yml up -d` |
| ~~3~~ | ~~prod self-build~~ | ~~（無受眾）~~ | **棄用** |

理由：路徑 3 沒有真正受眾（要本機跑 production image 的少見需求可改用 `docker build --target production -t local/test .` 後搭配 `CCAS_VERSION=local` 配 prod compose）。減少一條路徑 → 文件不再三方同步、新貢獻者不再卡在「該不該加 -f」。`docker-deploy.md` 對應規則由本 change 一併修訂。

### D2：Backend / worker / scheduler / bot 共用同一 image，frontend 與 proxy 各自獨立 image

選擇：發布三個 image — `ccas-backend`、`ccas-frontend`、`ccas-proxy`。backend image 同時被 worker、scheduler、bot service 引用，差別只在 `command:`；frontend image 只服務 React 靜態檔；proxy image 是唯一對外 nginx reverse proxy。

替代方案考慮：
- **每個 service 一個 image**（4 個 backend image）：被否決，build 時間與 registry 儲存四倍化，且後三者只是同一份 Python 程式不同 entrypoint。
- **單一 image 含 frontend 靜態檔**：被否決，frontend 是 nginx-served SPA，與 Python image base 完全不同，硬塞會破壞各自最佳化（multi-stage、size、scan surface）。
- **直接讓 frontend nginx 當唯一入口**：可行且最少服務數，但 ingress 規則會綁在 frontend image 內；未來若增加 Telegram webhook、setup callback、或獨立 API routing，會讓 frontend release 與 ingress policy 耦合。

理由：CCAS 既有 `backend/Dockerfile` 已經是 Python 通用 runtime，`command:` 切換成 worker / scheduler / bot 是現成模式，無需重構。新增 `ccas-proxy` 讓「對外 port / TLS 前置 / route policy」有單一責任邊界，frontend 與 backend 都變成內部服務。

**附帶 trade-off（image 邊界）**：單一 backend image 含 `--extra fubon-llm`（anthropic SDK + 相關依賴）會讓 worker / scheduler / bot 容器都帶上實際只有 backend captcha fallback 需要的依賴。實測 image 增量 < 50MB、registry 儲存可接受，且維持「四個 service 同 base」的營運單純性。若未來 LLM 依賴顯著膨脹（如加入大型本地模型），再評估是否分拆 backend-llm 為獨立 image。

### D3：image tag 策略採 `release` floating + `vMAJOR.MINOR.PATCH` 精確 + `vMAJOR` floating

選擇：
- main 分支 push → 推 `release`（floating）+ `sha-<short>`
- git tag `v0.1.0` push → 推 `v0.1.0`、`v0.1`、`v0`、`release`、`sha-<short>`
- `.env.example` 預設 `CCAS_VERSION=release`（讓初次使用者最容易上手），文件強烈建議生產環境改 `v0.1.0`

替代方案考慮：
- **僅精確 tag**：被否決，初次使用者要先去 GitHub Release 查最新版號才能跑，摩擦大。
- **Docker latest 慣例**：與 `release` 等價，但 immich 慣例是 `release`，與本 change 借鑒目標一致。

理由：對齊 immich，floating tag 降低首次門檻，精確 tag 給生產用，雙軌並存。

### D4：multi-arch 用 buildx + GitHub Actions cache（type=gha）

選擇：`docker/build-push-action@v5` 搭配 `platforms: linux/amd64,linux/arm64` 與 `cache-from/cache-to: type=gha`。

替代方案考慮：
- **僅 amd64**：被否決，Mac M 系列開發者實機跑 prod compose 會被 emulation 拖慢。
- **registry 自身 cache**（`type=registry`）：被否決，初版 registry 可能空、cache 命中率低。GHA cache 對單 repo 命中率最高。

風險：buildx GHA cache 上限 10GB，超過會 LRU 淘汰。本 change image 加總約 1-2GB，無風險。

### D5：config seed 採「example 範本 + entrypoint 自動複製」

選擇：發布 `config/*.example.yaml`，entrypoint 啟動時若偵測對應 `*.yaml` 不存在，從 example 複製一份並 log 警告「使用預設 config，請依需求調整」。

替代方案考慮：
- **首啟阻塞 + 要求使用者手動複製**：被否決，違反一鍵啟動目標。
- **example 直接當作 production config**：被否決，缺乏「使用者已知曉並調整過」的 audit trail。

理由：對齊 immich `UPLOAD_LOCATION` 預設值哲學 — 第一次能跑，第二次能改。

### D6：volume 掛載改用 `${CCAS_*_LOCATION:-./default}` 變數化

選擇：`.env` 暴露 `CCAS_DATA_LOCATION`、`CCAS_CONFIG_LOCATION`、`CCAS_LOG_LOCATION`，預設值為 `./data`、`./config`、`./logs`（相對於 compose 檔所在目錄）。compose 中以 `${CCAS_DATA_LOCATION:-./data}:/data` 形式掛載。

替代方案考慮：
- **named volume**：被否決，使用者備份/檢視成本高，與 immich 設計（讓使用者直接掛實體目錄）不一致。
- **寫死路徑**：被否決，無法支援外接磁碟、NAS 等需求。

注意：immich 文件警告「不支援網路掛載 SQLite/PostgreSQL data 目錄」。本 change `CCAS_DATA_LOCATION` 預設用於 SQLite WAL，使用者若掛網路檔系統需自行承擔，docs 會註明。

### D7：release 流程同步上傳 compose + env 範本到 GitHub Release artifact

選擇：在 release-docker workflow 結尾用 `softprops/action-gh-release@v2` 把 `docker/docker-compose.yml` + `docker/example.env` 附到 release 頁，使用者可直接 `curl -O` 下載。config templates 另打包進 backend image，避免使用者下載第三組檔案才能首次啟動。

### D8：Redis 持久化收斂到 `CCAS_DATA_LOCATION/redis`，不用 named volume

選擇：prod compose 將 redis service `volumes` 改為 `${CCAS_DATA_LOCATION:-./data}/redis:/data`。

替代方案考慮：
- **沿用 dev compose 的 named volume `ccas-redis`**：被否決，會破壞「備份單一 data 目錄即可恢復」的承諾，使用者必須額外用 `docker volume` 指令處理 RQ queue 狀態。
- **Redis 不持久化**：被否決，RQ failed registry 與重試排程需要 redis state，重啟丟失會導致殘存訊息或重複扣款偵測失準。

理由：對齊 immich「`UPLOAD_LOCATION` 是備份/搬遷的單一焦點」的設計哲學。所有持久化狀態（SQLite、staging PDF、log、redis dump）統一在 `CCAS_DATA_LOCATION` 子目錄，使用者只要備份這個目錄就保證完整。

### D9：Prod compose 單一外部入口策略（proxy 對外，backend / frontend / redis 全內部）

選擇：
- prod 版 `docker/docker-compose.yml` 新增 `proxy` service，image 為 `ghcr.io/<owner>/ccas-proxy:${CCAS_VERSION:-release}`，唯一 `ports:` 為 `${CCAS_PORT:-8080}:8080`。
- backend service **移除 `ports:` 區塊**，僅允許 docker network 內部存取 `backend:8000`。
- frontend service **移除 `ports:` 區塊**，僅允許 proxy 轉發 `frontend:8080`。
- redis service **移除 `ports:` 區塊**，僅允許 backend / worker / scheduler / bot 內部存取。
- proxy nginx routes：`/api/*` → `backend:8000`，其他路徑 → `frontend:8080`。未來若 Telegram webhook 或 OAuth callback 需要固定入口，新增 proxy route，不暴露 backend port。

替代方案考慮：
- **沿用 dev 的雙 port 暴露（backend 8000 + frontend 8080）**：被否決，使用者面對兩個 URL 不知何為主入口，且 backend port 無統一 proxy headers 處理。
- **直接讓 frontend nginx 對外**：可行，但 route policy 綁在 frontend image，Telegram webhook / OAuth callback 等非 frontend concern 會逐步污染 frontend image。
- **單一固定 port 8080**：被否決，與常見 self-host 服務（Jellyfin、Portainer、Adminer）衝突機率高，使用者改 port 是常見需求。

理由：對齊 immich 的「`IMMICH_PORT=2283` 單入口」UX，同時讓 backend、frontend、redis 都成為內部服務。這個決策妥當，因為它降低公開攻擊面，也讓日後 TLS、OAuth callback、webhook path 都有單一治理點。代價是多一個 proxy image 與一組 healthcheck，但比讓 backend port 外露更可控。

**附帶決策（D9.1）：proxy forwarding contract**

`docker/proxy/nginx.conf` SHALL 對所有反向代理 location 設定下列 headers，避免 cookie session、真實 client IP、未來即時推播失準：

```nginx
proxy_set_header Host              $host;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host  $host;
proxy_set_header X-Forwarded-Port  $server_port;
proxy_set_header X-Real-IP         $remote_addr;
# 為未來 SSE / WebSocket 預留
proxy_set_header Upgrade           $http_upgrade;
proxy_set_header Connection        $connection_upgrade;
proxy_http_version 1.1;
# 不覆寫 Set-Cookie 的 path / domain，讓瀏覽器原樣接受
proxy_pass_header  Set-Cookie;
```

理由：cookie session（`API_SESSION_COOKIE_NAME=ccas_session`）若 `Set-Cookie` 的 path 被 nginx 改寫，會造成登入後仍被 redirect 回 `/login` 的循環故障；後端日後若用 `X-Forwarded-Proto` 判斷 https、或用 `X-Forwarded-For` 寫入 audit log，缺 headers 會讓 IP 永遠是 `127.0.0.1`；`Upgrade` / `Connection upgrade` 為未來 D1 的 SSE 升級空間預留，現在不設後續加要動所有 location，反而違背「升級空間預留」承諾。

### D10：Telegram bot 預設納入 compose，設定齊全時必須可用

選擇：prod compose 中 bot service **不使用 profile**，隨 stack 一起啟動。啟動時檢查 Telegram 必要資訊：若 `TELEGRAM_BOT_TOKEN` 未設定，bot 進入 disabled idle 狀態、輸出明確 INFO、不 crashloop；若 token 已設定，bot 必須連線 Telegram 並通過 `getMe` healthcheck。通知目標 `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_CHAT_IDS` 依功能需要驗證，缺少時應讓對應通知或互動功能 fail loud。

替代方案考慮：
- **profile opt-in**：被否決。使用者填了 Telegram 變數後仍需要知道 `--profile telegram`，不符合「填妥需求資訊後功能必須可用」。
- **bot 始終啟動，token 為空時靜默 exit 0**：被否決，使用者會看到 service `exited (0)`，無法區分「未啟用」與「啟動失敗」，troubleshooting 訊號失真。
- **bot 始終啟動，token 為空時 crashloop**：被否決，restart loop 會在 `compose ps` 與 `logs` 持續產生噪音，違背「先把服務跑起來再慢慢設定」的單人 app 體驗。

理由：Telegram 對 CCAS 屬於必要整合能力，不應被 compose profile 藏起來。長輪詢模式不需要 nginx 對外 route；若未來改 webhook，新增 proxy route 即可，仍不暴露 bot/backend port。

### D11：`API_TOKEN` 首次啟動自動產生並落地到 secrets 目錄

選擇：backend image 內建共用 bootstrap 腳本，backend / worker / scheduler / bot 啟動時都先執行 token 載入邏輯；backend 額外執行 migration / seed / uvicorn，worker / scheduler / bot 則載入 token 後 exec 各自 command。bootstrap 在 alembic 之前加入 token 自動產生邏輯：
1. 偵測環境變數 `API_TOKEN` 為空時，呼叫 `openssl rand -hex 32` 產生新值
2. 寫入 `${CCAS_DATA_LOCATION:-/data}/secrets/api-token`（檔案權限 0600）
3. 將該值 `export` 進當前 process，後續服務沿用；worker / scheduler / bot 透過同一 data volume 讀取同一檔案
4. stdout 印出顯著訊息：`[INFO] 已自動產生 API_TOKEN，請至 /data/secrets/api-token 取得（首次啟動）`

替代方案考慮：
- **強制使用者填寫**：被否決，弱密碼風險高（觀察過實際使用者填 `password`、`123456`），且首次啟動 fail-fast 違反「pull 即用」承諾。
- **每次啟動產生新 token**：被否決，使用者已使用的舊 token 會失效，前端 / Telegram 整合會反覆斷線。
- **產生後寫回 .env**：被否決，需 entrypoint 有 host 端 .env 的寫入權限，且會修改使用者掛載檔案內容、踩到 docker secret 反 pattern。

理由：對齊 immich 的「首次安裝零摩擦」原則。使用者第一次 `up -d` 後從 secrets 目錄取得 token 即可登入，避免弱密碼。secrets 目錄與其他資料同在 `CCAS_DATA_LOCATION` 下，備份/搬遷一致。

### D11.1：首次登入 UX — API token 即 session 入口

**現況確認**：前端 `/login` 頁面（`frontend/src/pages/login.tsx:72`）接受一段 API token 字串，POST 到 `/api/auth/session`（`backend/src/ccas/api/routers/auth.py:72-84`）後，後端驗證 token 並 set cookie session（`ccas_session`，預設 12h）。**沒有獨立的 username/password、沒有 admin bootstrap wizard**，token 即為唯一登入憑證。

**串接決策**：D11 自動產生的 `${CCAS_DATA_LOCATION}/secrets/api-token` 與前端 `/login` 之間的 UX 接縫 SHALL 由 docs 明文寫出完整指令片段：

```bash
# 1. 取得自動產生的 token
cat "${CCAS_DATA_LOCATION:-./data}/secrets/api-token"

# 2. 開瀏覽器至 http://localhost:${CCAS_PORT:-8080}/login

# 3. 將上一步輸出的 token 貼入欄位、登入即可
```

替代方案考慮：
- **新增 `/setup` 引導頁顯示 token**：被否決。後端要實作「是否為首次啟動」狀態與一次性顯示邏輯，超出本 change scope；且 token 已落地 secrets 檔，再從 Web 顯示反而多一條洩漏面。
- **第一次 `up -d` 後 stdout 印 token**：對 docker compose 使用者不直觀（要 `docker compose logs backend` 翻），且 log 會被 RedactingFilter 蓋掉。落地 secrets 檔 + docs 指令片段最直接。
- **內建預設 token**：被否決，弱密碼風險與 immich `IMMICH_API_KEY` 設計衝突。

理由：這個決策只是「把已通的路徑寫成 spec」，避免使用者照 quickstart 走完 `docker compose up -d` 後不知如何登入。Cost 為零（不動 code），benefit 為消除 onboarding 卡點。

### D11.2：dev / prod API base path 統一

**現況確認**：前端 `frontend/src/lib/api-client.ts:5` 已是 `const API_BASE = import.meta.env.VITE_API_BASE ?? ''`，預設空字串走相對 `/api/*` 路徑；dev 透過 `vite.config.ts:14-18` 的 proxy 轉到 `127.0.0.1:8000`，prod 透過 nginx proxy 轉到 `backend:8000`。兩條路徑都假設「frontend 與 backend 同源」。

**決策**：

1. **前端 SHALL 用相對 `/api/*` 路徑**，prod build 時 `VITE_API_BASE` SHALL 為空字串、frontend bundle 內 SHALL 不含絕對 backend URL。理由：使用者改 `CCAS_PORT=12283` 不需要 rebuild frontend image，只是 nginx 對外 port 改變；若 bundle 內含絕對 URL，每次改 port 都要重 build image，違背「pull 即用」承諾。
2. **prod 模式下 frontend 與 backend 同源**（皆走 `localhost:${CCAS_PORT}`），CORS pre-flight SHALL 不發生。`docker/example.env` 的 `FRONTEND_ORIGINS` 註解 SHALL 明示「prod 同源時可留空、開發時才需要 `localhost:5173,localhost:8080`」。
3. **不動 backend CORS 邏輯**（不引入「同源放寬」的 condition），保持單一 SSOT 為 `FRONTEND_ORIGINS` env，避免 conditional CORS 的隱性故障。

替代方案：
- **backend CORS 同源時自動放寬**：被否決，引入隱性條件後 troubleshooting CORS 失敗會多一條「是不是被同源邏輯吃掉了」分支。
- **`VITE_API_BASE` 預設絕對 URL（如 `http://localhost:8080/api`）**：被否決，違背「改 port 不重 build」目標。

理由：固化現有設計，避免實作期有人「順手」改成絕對 URL 或加 conditional CORS。

### D12：backend image 必須自含 entrypoint 與 default config templates

選擇：`backend/Dockerfile` production target copy `scripts/docker-entrypoint.sh`、`scripts/check-env.sh` 與 `config/*.example.yaml` 到 image 內，例如 `/app/docker-entrypoint.sh`、`/app/check-env.sh`、`/app/default-config/*.yaml`。prod compose 不再掛載 repo 根目錄 `./scripts` 或 `./.env.example`，因為終端使用者不持有 source tree。

替代方案考慮：
- **要求使用者下載 scripts 與 config examples**：被否決，會把「兩份檔案啟動」擴散成多檔案同步問題。
- **跳過 env validation / seed**：被否決，會讓首次啟動錯誤變晚、訊息更差。

理由：純 image pull 的核心前提是 image 自含啟動所需程式與預設資料；host 只提供 `.env` 與持久化 volume。

D7 替代方案考慮：
- **要求使用者 git clone**：被否決，違背「不需要原始碼」目標。
- **發布到專屬 CDN**：被否決，過度工程。

## Risks / Trade-offs

- **Release workflow 首次啟用需手動授權 GHCR push**：fork / 新 repo 第一次推時 GHCR 自動建立 package，但 default visibility 為 private。Mitigation：在 docs/upgrade-guide.md 記錄手動切換 public 的步驟，workflow 不嘗試自動處理（GitHub API 需 admin token）。
- **`release` floating tag 易讓使用者誤升級踩到破壞性變更**：Mitigation：docs 強烈建議 production 用精確 tag、breaking change 必須升 major、CHANGELOG 強制要求。
- **多架構 build 時間延長 1.5-2 倍**：Mitigation：GHA cache 命中後增量 build；release tag push 才跑多架構，main push 只跑 amd64。
- **entrypoint 自動複製 config example 可能掩蓋設定錯誤**：Mitigation：複製時 WARN log 含明顯標記，docs/install-quickstart.md 把「檢查 config」列為必要步驟。
- **既有開發者誤拿到發布版 compose**：Mitigation：發布版檔名與位置（`docker/docker-compose.yml`）與 dev 版（根目錄 `docker-compose.yaml`）區隔；docs 明確指引兩者用途。
- **`CCAS_VERSION=release` 在 image 還沒推上去前 pull 會失敗**：Mitigation：第一次發 release tag 之前不 advertise 安裝指引；release-docker workflow 跑通並驗證 pull 成功後再更新 README。
- **🔴 Gmail OAuth 是現階段安裝體驗最大瓶頸，本 change 不解決**：使用者必須先到 Google Cloud Console 建立 OAuth client、下載 `credentials.json`、再透過 CLI（`python -m ccas.tools.gmail_auth`）取得 `token.json`。整個流程需技術背景且無法純 container 完成（CLI 依賴 `localhost:0` 的 OAuth callback，container 內難以打通）。Mitigation：(1) `docs/install-quickstart.md` 必須含完整 Gmail 設定章節（連結至 `docs/gmail-setup.md`），明示為前置條件。(2) README 不得使用「一鍵安裝」「無需設定」措辭。(3) 真正的「pull-and-run」體驗依賴後續 `oauth-onboarding-ui` change 提供 Web UI 取代 CLI flow。
- **API_TOKEN 自動產生機制必須避免覆蓋既有值**：使用者既有部署若 `.env` 已設定 `API_TOKEN`，entrypoint 不得覆寫；secrets 檔已存在時也應優先讀取既有值而非重產。Mitigation：entrypoint 邏輯為三段式 — (a) 環境變數已設定 → 直接使用、(b) secrets 檔存在 → 讀取載入、(c) 兩者皆無 → 產生新值並落地。寫單元測試覆蓋三條路徑。
- **單一外部 port 收斂後 troubleshooting 路徑改變**：使用者過去可能直接 `curl localhost:8000/health`；改 prod compose 後 backend 不暴露 host port。Mitigation：quickstart 與 docker-deploy.md 的 troubleshooting 段落改為 `docker compose exec backend curl localhost:8000/health`，或一律走 frontend `:CCAS_PORT/api/health`。
- **rules 漂移風險（`.claude/rules/docker-deploy.md` vs spec）**：rules 仍規定「生產部署：務必以 `docker compose -f docker-compose.yaml up -d` 明確指定 base compose，略過 override」，本 change D1 已棄用此路徑。若實作期先改 compose 再改 rules，hooks 與 ECC agent 會用舊規則攔截 PR、產生噪音。Mitigation：tasks §5.5（修訂 `docker-deploy.md`）SHALL **先於 §1 compose 落地或同 PR 同 commit**；落地順序在 PR description 明示，code review 必須驗證 rules 與 compose 改動同步。

## Migration Plan

1. **不影響既有部署**：本 change 只新增檔案、修改 `.env.example` 與 entrypoint 自動複製邏輯。既有以 `docker-compose.yaml` 啟動的開發者環境零變動。
2. **首次發 release**：合 PR → 在 develop 驗證 → tag `v0.1.0-rc.1` 觸發 release-docker workflow → 在乾淨機器拉 `docker/docker-compose.yml` + `docker/example.env` 驗證一鍵啟動 → 通過後正式 tag `v0.1.0`。
3. **回滾**：若 release-docker workflow 失敗，僅影響未來新使用者，既有部署不受影響。直接 revert PR 即可。
4. **README 公告**：等 v0.1.0 image 確定可被外部 pull 後再更新 README「30 秒安裝」段落，避免指向不存在的 image。

## Open Questions

- GitHub repo 的 owner 名稱（影響 `ghcr.io/<owner>/...` 路徑）— 將由 `${{ github.repository_owner }}` 動態解析，無需手動填入。
- 是否在 release-docker workflow 加上 cosign 簽章 — 列為 future enhancement，本 change 不做。
- **`oauth-onboarding-ui` 後續 change scope（已釘清）**：本 change 採 env-driven 設定 + entrypoint 自動產生 secret 的折衷做法；後續 `oauth-onboarding-ui` change SHALL 覆蓋四件事，避免該 change 範疇漂移：(a) Gmail OAuth Web flow 取代 CLI、(b) bank 啟用清單 UI（取代手動編輯 `banks.yaml`）、(c) PDF 密碼 UI（取代 env `PDF_PASSWORD_*`）、(d) 首次 admin / API token rotate UI（取代手動 `cat secrets/api-token`）。compose-pull-deploy 的 `installation-quickstart` capability 為其入口前置依賴。
- **bank 啟用與 PDF 密碼仍綁 yaml/env 的揭露**：本 change 不在 UI 化這條，但 `install-quickstart.md` SHALL 在「設定 .env」步驟誠實揭露 `PDF_PASSWORD_*` 仍需手動填入、`banks.yaml` 啟用清單仍需手動編輯，並轉述 `oauth-onboarding-ui` 將補洞。`banks.example.yaml` SHALL 預設啟用全部支援銀行（讓 pipeline 自行 skip 無 PDF 者），降低首次操作門檻。
