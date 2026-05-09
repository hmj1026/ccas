## Why

CCAS 已具備完整的 Docker 化基礎建設（multi-stage Dockerfile、healthcheck、prod/dev override、entrypoint 自動 migration 與 seeding），但終端使用者仍無法用 `docker compose pull && docker compose up -d` 一鍵啟用：image 沒發布到 registry、`docker-compose.yaml` 內含 `build:` 區塊強迫使用者持有原始碼、config seed 檔缺 example、版本管理沒有對齊 image tag。本 change **對齊 immich 的 image / compose 發布慣例**，把這道從「要 build」到「pull 即用」的最後一哩補齊。注意：本 change 範圍限於分發機制與安裝路徑，**不解決 Gmail OAuth 等外部相依設定流程**（屬於後續 `oauth-onboarding-ui` 範圍），install-quickstart 須誠實揭露 Gmail 前置設定為使用者自行完成項目。

## What Changes

- 新增發布版 compose 檔 `docker/docker-compose.yml`，僅引用 `image:` 不含 `build:`，使用 `${CCAS_VERSION:-release}` pin tag。**外部 port 收斂為單一 nginx reverse proxy 入口**：新增 `proxy` service 對外暴露 `${CCAS_PORT:-8080}`，backend / frontend / redis 皆不對 host 暴露 port，所有 Web / API 請求經 proxy 轉入內部 service。**proxy nginx config SHALL 包含標準 reverse proxy headers forwarding**（`X-Forwarded-For/Proto/Host/Port`、`Host`、保留 `Set-Cookie` path、`Upgrade` / `Connection upgrade` 為未來 SSE / WebSocket 預留），確保 cookie session、真實 client IP、未來即時推播皆正確運作。**Redis 持久化改用 bind mount** `${CCAS_DATA_LOCATION}/redis:/data`，不再使用 named volume，確保「備份單一 data 目錄」承諾完整。**Telegram bot service 預設納入 compose**：未填 token 時以 disabled 狀態清楚記錄、不影響其他服務；使用者填妥 Telegram 必要資訊後，bot 必須自動啟動並可用，不需額外 `--profile`。
- 新增 `docker/example.env`，對應發布版 compose 的最小必要變數集，含 inline 註解與必填/選填標記。
- 新增 `.github/workflows/release-docker.yaml`，於 push tag `v*` 與 push branch `main` 時建置並推送 GHCR：
  - Image：`ghcr.io/<owner>/ccas-backend`、`ghcr.io/<owner>/ccas-frontend`、`ghcr.io/<owner>/ccas-proxy`
  - Tag：`release`（main）、`v0.1.0`（精確）、`v0`（major floating）、`sha-<short>`（debug）
  - 多架構：`linux/amd64` + `linux/arm64`
- 新增 `config/banks.example.yaml`、`config/bank-code-registry.example.yaml`、`config/categories.example.yaml`，並將啟動腳本與 default config templates 打包進 backend image；`scripts/docker-entrypoint.sh` 在對應檔不存在時自動從 image 內建 template 複製。**`API_TOKEN` 未設定時共用 bootstrap 自動產生 32-byte random hex 並落地到 `${CCAS_DATA_LOCATION}/secrets/api-token`**，backend / worker / scheduler / bot 皆會載入同一份 token，避免只有 backend 看得到 secret。
- `.env.example` 新增 `CCAS_VERSION`、`CCAS_DATA_LOCATION`、`CCAS_CONFIG_LOCATION`、`CCAS_LOG_LOCATION`、`CCAS_PORT`；現有變數補齊註解。
- 新增 `docs/install-quickstart.md`（純 pull 使用者視角五步驟啟動）、`docs/upgrade-guide.md`（版本升級 SOP 與相容性政策）。
- `README.md` 加入「30 秒安裝」段落並指向 quickstart；既有 `docs/deployment-guide.md` 重新定位為「進階 / 自建 build」。
- 既有 `docker-compose.yaml`（含 `build:`）正式定位為「**僅開發**」，行為不變。
- **收斂啟動路徑為兩種**：`docker-compose.yaml`（dev：本地 build + override 自動載入）、`docker/docker-compose.yml`（prod：純 image pull）。先前的「prod self-build」中間路徑（`docker compose -f docker-compose.yaml up -d` 跳 override）SHALL **被棄用**，相關規則從 `.claude/rules/docker-deploy.md` 移除，文件改用「自建 image：手動 `docker build` + `CCAS_VERSION=local`」段落取代。

不在本 change 範圍內：Docker Hub 第二發布站、Docker secrets `_FILE` 模式。**`oauth-onboarding-ui` 後續 change 將涵蓋四件事**（在此明文釘清 scope 避免漂移）：(a) Gmail OAuth Web flow 取代 CLI `python -m ccas.tools.gmail_auth`、(b) bank 啟用清單 UI（取代手動編輯 `banks.yaml`）、(c) PDF 密碼 UI（取代 env 變數 `PDF_PASSWORD_*`）、(d) 首次 admin / API token rotate UI（取代手動 `cat secrets/api-token`）。

## Capabilities

### New Capabilities
- `installation-quickstart`: 終端使用者僅需下載 `docker-compose.yml` + `.env`、編輯必要變數，執行 `docker compose pull && docker compose up -d` 即啟動完整服務的安裝體驗，包含首次啟動引導、**首次登入 UX（從 `${CCAS_DATA_LOCATION}/secrets/api-token` 取得 token → 貼到 `/login` 頁面換 cookie session）**、誠實揭露目前仍需手動編輯的設定項目（PDF 密碼、`banks.yaml` 啟用清單），與升級 SOP。**前置條件**：使用者須先完成 Gmail OAuth 設定（取得 `credentials.json`），文件不得宣稱「無需設定」「一鍵安裝」等措辭。
- `image-publishing`: 將 backend / frontend image 自動建置並發布到 GHCR 的 release pipeline，含 tag 策略、多架構支援、release artifact 同步上傳。

### Modified Capabilities
- `docker-deployment`: 新增「compose 檔案分流（dev 含 build / prod 純 pull）」與「`CCAS_*_LOCATION` 環境變數作為 volume 掛載來源」要求；既有 staging 路徑相關要求不動。
- `env-validation`: `.env.example` SSOT 範圍擴充至新變數（`CCAS_VERSION`、三組 `*_LOCATION`），驗證腳本須涵蓋。

## Impact

- **新檔案**：`docker/docker-compose.yml`、`docker/example.env`、`docker/proxy/Dockerfile`、`docker/proxy/nginx.conf`、`.github/workflows/release-docker.yaml`、`config/*.example.yaml`、`docs/install-quickstart.md`、`docs/upgrade-guide.md`
- **修改**：`.env.example`、`backend/Dockerfile`、`scripts/docker-entrypoint.sh`、`README.md`、`docs/deployment-guide.md`（重新定位）
- **不動**：`docker-compose.yaml`（dev）、`docker-compose.override.yml`、`backend/src/`、`frontend/src/`
- **CI/CD**：新增 GHCR push 權限需求（`packages: write`）、release workflow 觸發條件擴增。
- **使用者影響**：現有開發者工作流（`docker compose up`）無變化；新使用者多一條「下載 compose + env 即可」的安裝路徑。
- **依賴**：無新 runtime 依賴。GitHub Actions 端新增 `docker/login-action`、`docker/setup-buildx-action`、`docker/build-push-action`。
- **後續 change 銜接**：`oauth-onboarding-ui` 將以本 change 落地的 `installation-quickstart` capability 為基礎，補上 `/setup` 前端頁與 `/api/setup/*` API。
