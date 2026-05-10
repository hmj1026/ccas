# docker-deployment Specification

## Purpose

確保 Docker（`STAGING_DIR=/data/staging`）與本機（`STAGING_DIR=./data/staging`）兩種部署環境下，`staged_attachments.staged_path` 都能一致定位檔案。透過 `staged_path` 只儲存相對於 `STAGING_DIR` 的相對路徑、使用時動態組合為完整路徑，並提供 idempotent migration script 將既有絕對路徑記錄轉換為相對路徑，避免跨環境執行時 attachment 找不到。

## Requirements

### Requirement: Staging 路徑跨環境一致性

`staged_attachments.staged_path` SHALL 儲存相對於 `STAGING_DIR` 的相對路徑（如 `FUBON/xxx.pdf`），而非絕對路徑。使用時 SHALL 以 `Path(settings.staging_dir) / staged_path` 組合為完整路徑。

#### Scenario: 新建 staging record 使用相對路徑
- **WHEN** ingest job 建立新的 `StagedAttachment` record
- **THEN** `staged_path` SHALL 為相對路徑格式（如 `FUBON/msg123_file.pdf`），不含 STAGING_DIR prefix

#### Scenario: 讀取時動態組合完整路徑
- **WHEN** decrypt job 或 parse job 讀取 `staged_path`
- **THEN** SHALL 以 `Path(settings.staging_dir) / staged_path` 取得完整檔案路徑

#### Scenario: Docker 與本機環境均可正常存取
- **WHEN** 同一筆 staging record 在 Docker（`STAGING_DIR=/data/staging`）與本機（`STAGING_DIR=./data/staging`）執行
- **THEN** 兩環境 SHALL 皆能正確定位檔案

#### Scenario: 既有記錄 migration
- **WHEN** 執行路徑 migration script
- **THEN** 既有的絕對路徑 record SHALL 被轉換為相對路徑，script SHALL 為 idempotent（重複執行不重複修改）

### Requirement: Compose 檔案分流（dev 含 build / prod 純 pull）

系統 SHALL 維護兩份 docker compose 檔案以區分使用情境：(1) 根目錄 `docker-compose.yaml` 含 `build:` 區塊，供開發者本地修改後重 build；(2) `docker/docker-compose.yml` 僅含 `image:` 指令，供終端使用者透過 GHCR 直接 pull。兩檔 SHALL 共用相同核心 service 名稱與 volume 慣例；prod compose 另新增 `proxy` service 作為唯一對外入口。

#### Scenario: 開發者持續使用既有 dev compose

- **WHEN** 開發者於 repo 根目錄執行 `docker compose up`
- **THEN** docker SHALL 讀取 `docker-compose.yaml` + `docker-compose.override.yml`，從本地原始碼 build image，行為與本 change 前完全一致

#### Scenario: 終端使用者使用 prod compose

- **WHEN** 終端使用者執行 `docker compose -f docker/docker-compose.yml up -d`
- **THEN** docker SHALL 從 GHCR pull image 啟動 service，過程不需要 repo 原始碼

#### Scenario: 兩份 compose service 名稱一致

- **WHEN** 比對兩份 compose 檔案
- **THEN** service 名稱（backend、worker、scheduler、bot、frontend、redis）SHALL 完全相同，避免文件與 troubleshooting 流程分歧

### Requirement: CCAS_*_LOCATION 變數化 volume 掛載

Prod 版 `docker/docker-compose.yml` SHALL 透過 `${CCAS_DATA_LOCATION:-./data}`、`${CCAS_CONFIG_LOCATION:-./config}`、`${CCAS_LOG_LOCATION:-./logs}` 三個變數定義 host 端 volume 路徑。三個變數 SHALL 在 `docker/example.env` 暴露並提供預設值。

#### Scenario: 預設值可即用

- **WHEN** 使用者未在 `.env` 設定任何 `CCAS_*_LOCATION` 變數
- **THEN** docker compose SHALL 在當前目錄建立 `./data`、`./config`、`./logs` 並掛載

#### Scenario: 自訂路徑支援外接磁碟

- **WHEN** 使用者於 `.env` 設定 `CCAS_DATA_LOCATION=/mnt/external/ccas-data`
- **THEN** docker compose SHALL 將該絕對路徑掛載為容器內 `/data`

#### Scenario: 路徑變更不影響容器內 path

- **WHEN** 使用者變更 `CCAS_DATA_LOCATION` 的值並重新 `docker compose up -d`
- **THEN** 容器內路徑 SHALL 仍為 `/data`（不變），應用程式碼無需感知 host 路徑變化

### Requirement: 寫 SQLite 的 service 共用同一 data volume

所有對 SQLite 進行寫入的 service（backend、worker、scheduler、bot）SHALL 在同一份 compose 檔內掛載**同一個** host 目錄為容器內 `/data`。dev compose 該目錄 SHALL 為 `./backend/data`；prod compose（`docker/docker-compose.yml`）該目錄 SHALL 為 `${CCAS_DATA_LOCATION:-./data}`。任何寫入 SQLite 的 service 不得使用獨立 volume 或不同的 host 路徑。

#### Scenario: 四個寫入 service 路徑一致

- **WHEN** 檢視 `docker/docker-compose.yml` 中 backend、worker、scheduler、bot 四個 service 的 volumes 區塊
- **THEN** 四者 SHALL 皆含 `${CCAS_DATA_LOCATION:-./data}:/data` 條目，host 端解析後路徑完全相同

#### Scenario: 跨 process SQLite 讀寫一致性

- **WHEN** worker process 寫入 `pipeline_runs` row、backend process 接著查詢同一 row
- **THEN** backend SHALL 能立即讀到最新 row 內容（透過共用 SQLite WAL 檔）

#### Scenario: 變更 CCAS_DATA_LOCATION 同步生效

- **WHEN** 使用者在 `.env` 改變 `CCAS_DATA_LOCATION` 後 `docker compose up -d`
- **THEN** 四個寫入 service 的 host 掛載 SHALL 同步切換到新路徑，不得有任一 service 仍指向舊路徑

### Requirement: 版本變數 CCAS_VERSION pin image tag

Prod 版 compose 檔的所有 service image SHALL 以 `image: ghcr.io/<owner>/<name>:${CCAS_VERSION:-release}` 形式引用，使用者透過修改 `.env` 中 `CCAS_VERSION` 即可切換版本而不需修改 compose 檔。

#### Scenario: 切換版本僅需改 .env

- **WHEN** 使用者將 `.env` 中 `CCAS_VERSION` 從 `v0.1.0` 改為 `v0.2.0` 並執行 `docker compose pull && docker compose up -d`
- **THEN** 所有 service SHALL 升級到 v0.2.0 image，無需修改任何 compose 或腳本

#### Scenario: backend 與 frontend 版本同步

- **WHEN** `.env` 設定 `CCAS_VERSION=v0.1.0`
- **THEN** backend 與 frontend image SHALL 同時被 pin 到 `v0.1.0`，避免使用者手動同步兩個版本變數

### Requirement: Prod compose 單一 nginx reverse proxy 外部入口

Prod 版 `docker/docker-compose.yml` SHALL 新增 `proxy` service，使用 `ghcr.io/<owner>/ccas-proxy:${CCAS_VERSION:-release}` image，且它 SHALL 是唯一宣告 host `ports:` 的 app service。`proxy` SHALL 以 `${CCAS_PORT:-8080}:8080` 對外服務，並透過 docker internal network 將 `/api/*` 反向代理至 `backend:8000`，其餘 Web 路徑反向代理至 `frontend:8080`。backend、frontend、redis、worker、scheduler、bot SHALL 不對 host 暴露任何 port。

#### Scenario: backend 不直接對外

- **WHEN** prod compose 啟動後執行 `curl http://localhost:8000/health`（host 端）
- **THEN** 連線 SHALL 被拒絕（connection refused），因 backend port 未對 host 暴露

#### Scenario: frontend 不直接對外

- **WHEN** prod compose 啟動後執行 `curl http://localhost:8080/health` 且 `CCAS_PORT` 非 8080
- **THEN** 若 host 端未另行映射 8080，連線 SHALL 被拒絕，因 frontend port 未對 host 暴露

#### Scenario: 外部請求經 proxy 反向代理

- **WHEN** prod compose 啟動後執行 `curl http://localhost:${CCAS_PORT}/api/health`
- **THEN** proxy nginx SHALL 將請求反向代理至 `backend:8000/health` 並回 200

#### Scenario: 自訂對外 port

- **WHEN** 使用者於 `.env` 設定 `CCAS_PORT=12283`
- **THEN** prod compose SHALL 將 proxy 暴露於 host `12283`，container 內仍為 8080

#### Scenario: proxy healthcheck 代表 ingress 可用

- **WHEN** proxy service healthcheck 執行
- **THEN** healthcheck SHALL 驗證 proxy 本身可回應 `/health`，且 `/api/health` 可成功轉發至 backend

### Requirement: 持久化狀態統一收斂於 CCAS_DATA_LOCATION

Prod 版 compose 的所有持久化狀態（含 SQLite、staging PDF、log、redis dump、自動產生的 secrets）SHALL 全數落於 `${CCAS_DATA_LOCATION}` 子目錄下，**不得**使用 docker named volume。使用者備份單一 `CCAS_DATA_LOCATION` 目錄 SHALL 足以完整還原所有持久化資料。

#### Scenario: redis 採 bind mount 而非 named volume

- **WHEN** 檢視 `docker/docker-compose.yml` 的 redis service volumes
- **THEN** SHALL 為 `${CCAS_DATA_LOCATION:-./data}/redis:/data` 形式，**不得**含 `ccas-redis` 等 named volume 宣告

#### Scenario: 備份恢復完整性

- **WHEN** 使用者 `tar -czf backup.tar.gz "${CCAS_DATA_LOCATION}"` 後 `docker compose down`、刪除 data 目錄、解壓 backup、`docker compose up -d`
- **THEN** 系統 SHALL 完整還原（含 SQLite 資料、Gmail token、API_TOKEN、redis state、staging 檔），無資料遺失

### Requirement: Telegram bot 預設納入 compose 且設定齊全即啟用

Prod 版 compose 的 bot service SHALL 不使用 `profiles`，預設 `docker compose up -d` 會建立 bot service。當 `TELEGRAM_BOT_TOKEN` 未設定時，bot SHALL 進入 disabled idle 狀態並輸出明確 INFO，不得 crashloop；當使用者填妥 Telegram 必要資訊後，bot SHALL 自動啟動並通過 healthcheck，不需要額外 compose profile 或額外命令。

#### Scenario: 未設定 Telegram 時不干擾其他服務

- **WHEN** 使用者執行 `docker compose -f docker/docker-compose.yml up -d` 且 `.env` 未設定 `TELEGRAM_BOT_TOKEN`
- **THEN** bot service SHALL 不 crashloop，logs SHALL 顯示 Telegram disabled，backend / worker / scheduler / frontend / proxy / redis 正常啟動

#### Scenario: 填妥 Telegram 後自動可用

- **WHEN** 使用者於 `.env` 填妥 `TELEGRAM_BOT_TOKEN` 與必要的 chat / allowlist 設定後執行 `docker compose up -d`
- **THEN** bot service SHALL 啟動並通過 healthcheck（Telegram `getMe` API 200）

#### Scenario: Telegram 不需要 host port

- **WHEN** bot 使用 Telegram long polling 模式
- **THEN** bot SHALL 不宣告 host `ports:`；若未來改 webhook，外部 webhook path SHALL 經 proxy nginx route，不得直接暴露 backend 或 bot port

### Requirement: worker / scheduler / bot 健康檢查

Prod 版 compose 中 worker、scheduler、bot、proxy 四個 service SHALL 各自宣告 healthcheck 指令，避免「`running` 但實際失能」。worker SHALL 透過 `rq info` 連線 redis 確認 queue 可消化、scheduler SHALL 透過 heartbeat 檔最近寫入時間判斷、bot SHALL 在 token 已設定時透過 Telegram `getMe` API 驗證 token 有效、proxy SHALL 驗證 `/health` 與 `/api/health`。

#### Scenario: worker 健康檢查反映 redis 連線

- **WHEN** redis 已停止，worker 嘗試健康檢查
- **THEN** healthcheck SHALL 回 unhealthy，`docker compose ps` 顯示 worker 狀態異常

### Requirement: Backend image 自含啟動腳本與 default config templates

Prod backend image SHALL 自含啟動所需腳本與 default config templates，不得依賴使用者持有 repo source tree。`backend/Dockerfile` SHALL 將 `scripts/docker-entrypoint.sh`、`scripts/check-env.sh`、`.env.example` 或等價 env schema、以及 `config/*.example.yaml` 複製進 image。prod compose SHALL 不掛載 `./scripts` 或 `./.env.example`。

#### Scenario: 乾淨目錄無 source tree 仍可啟動 backend

- **WHEN** 使用者在乾淨目錄只有 `docker-compose.yml` 與 `.env`
- **THEN** backend container SHALL 能找到 entrypoint、env validation schema、default config templates，並完成 token bootstrap、config seed、alembic migration

#### Scenario: config templates 從 image 複製到 mounted config

- **WHEN** `${CCAS_CONFIG_LOCATION}/banks.yaml` 不存在
- **THEN** entrypoint SHALL 從 image 內建 default config template 複製到 `${CCAS_CONFIG_LOCATION}/banks.yaml`，而非依賴 host 上已存在 `banks.example.yaml`

### Requirement: Proxy 反向代理 headers forwarding contract

`docker/proxy/nginx.conf` SHALL 對所有反向代理 location 設定標準 reverse proxy headers，確保 cookie session、真實 client IP 與未來即時推播（SSE / WebSocket）皆正確傳遞。最低必要 headers 包含：`Host`、`X-Forwarded-For`、`X-Forwarded-Proto`、`X-Forwarded-Host`、`X-Forwarded-Port`、`X-Real-IP`、`Upgrade`、`Connection`（搭配 `proxy_http_version 1.1`）。`Set-Cookie` SHALL 不被 proxy 覆寫 path 或 domain。

#### Scenario: backend 透過 X-Forwarded-Proto 判斷 https 不被截斷

- **WHEN** 使用者透過 TLS 終結器（未來 enhancement）連入 proxy、proxy 內部以 http 轉發至 backend
- **THEN** backend 收到的 request SHALL 含 `X-Forwarded-Proto: https`，使後端日後產生 absolute URL（如 OAuth callback）時能用正確 scheme

#### Scenario: 登入後 Set-Cookie 保留 path 並讓瀏覽器接受

- **WHEN** 使用者於 `/login` 頁貼 token POST `/api/auth/session`，backend 回 `Set-Cookie: ccas_session=...; Path=/; HttpOnly`
- **THEN** proxy SHALL 不覆寫 cookie path / domain，瀏覽器 SHALL 接受 cookie 並在後續請求帶回；使用者 SHALL 不被 redirect 回 `/login` 循環

#### Scenario: 後端透過 X-Forwarded-For 取得真實 client IP

- **WHEN** 外部使用者請求進入 proxy、proxy 轉發至 backend
- **THEN** backend access log 中的 client IP SHALL 為使用者實際 IP（透過 `X-Forwarded-For` header）而非 `127.0.0.1`（proxy 內部 IP）

#### Scenario: WebSocket / SSE upgrade headers 不被 proxy 吃掉

- **WHEN** 未來新增 SSE endpoint，client 發送 `Upgrade: <protocol>` request
- **THEN** proxy SHALL 透過 `proxy_set_header Upgrade $http_upgrade` 與 `proxy_set_header Connection "upgrade"` 完整轉發 headers、`proxy_http_version 1.1` 確保連線可升級；本 change 雖不實作 SSE，但 nginx config SHALL 已預留此能力

### Requirement: 前端 API base path 為相對路徑

Frontend production build 時 `VITE_API_BASE` SHALL 為空字串，所有 API 呼叫 SHALL 走相對 `/api/*` 路徑。Frontend bundle 內 SHALL 不含絕對 backend URL，使用者改 `CCAS_PORT` 不需要 rebuild frontend image。

#### Scenario: prod build 時 VITE_API_BASE 為空字串

- **WHEN** GHCR 發布的 `ccas-frontend` image 被 inspect / 解壓
- **THEN** 產出 bundle SHALL 不含類似 `http://backend:8000` 或 `http://localhost:8000` 的硬編 backend URL，所有 API 呼叫 SHALL 為相對路徑

#### Scenario: 改 CCAS_PORT 不需要重 build frontend image

- **WHEN** 使用者於 `.env` 將 `CCAS_PORT` 從 `8080` 改為 `12283` 並執行 `docker compose up -d`
- **THEN** 系統 SHALL 在新 port 上提供完整服務、frontend image 不需要 rebuild、proxy 對外 port 變更為 `12283`、frontend bundle 不變

### Requirement: CORS 在 proxy 同源情境的處理

Prod 模式下 frontend 與 backend 同源（皆走 `localhost:${CCAS_PORT}`），CORS pre-flight SHALL 不發生。`docker/example.env` 的 `FRONTEND_ORIGINS` 註解 SHALL 明示「prod 同源時可留空、開發時才需要 `localhost:5173,localhost:8080`」。Backend CORS 邏輯 SHALL **不**引入「同源時自動放寬」的 conditional 分支，保持單一 SSOT 為 `FRONTEND_ORIGINS` env。

#### Scenario: prod 同源情境無 CORS pre-flight

- **WHEN** 使用者透過 prod compose 啟動，瀏覽器訪問 `http://localhost:${CCAS_PORT}`、頁面內 fetch `/api/health`
- **THEN** request SHALL 不觸發 CORS pre-flight（同源），即使 `FRONTEND_ORIGINS` 留空也能正常運作

#### Scenario: example.env 註解明示 FRONTEND_ORIGINS 用途

- **WHEN** 檢視 `docker/example.env` 的 `FRONTEND_ORIGINS` 段落
- **THEN** 註解 SHALL 明示「prod 同源時可留空、開發時才需要設定 dev 來源」，避免使用者誤以為必填

#### Scenario: backend CORS 邏輯保持簡單

- **WHEN** code review backend CORS 設定
- **THEN** backend SHALL 僅依 `FRONTEND_ORIGINS` env 設定 allowed origins，**不**引入「request origin 等於 server origin 時自動放寬」的 conditional 邏輯
