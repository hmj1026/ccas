## ADDED Requirements

### Requirement: GHCR 自動發布工作流

系統 SHALL 提供 `.github/workflows/release-docker.yaml`，於下列觸發條件執行 image 建置與發布到 GitHub Container Registry：(1) push tag 符合 `v*`，(2) push branch `main` 或 `master`。Workflow SHALL 建置並發布 `ccas-backend`、`ccas-frontend`、`ccas-proxy` 三個 image。Workflow SHALL 使用 `GITHUB_TOKEN` 認證 GHCR 與建立 GitHub Release、不得在 source 中硬編 token，且 SHALL 宣告 `permissions: contents: write, packages: write`。

#### Scenario: tag 觸發完整版本發布

- **WHEN** 開發者執行 `git tag v0.1.0 && git push origin v0.1.0`
- **THEN** workflow SHALL 建置 `ccas-backend`、`ccas-frontend`、`ccas-proxy` image 並推送到 `ghcr.io/<owner>/ccas-backend`、`ghcr.io/<owner>/ccas-frontend`、`ghcr.io/<owner>/ccas-proxy`

#### Scenario: main 分支觸發 release floating tag

- **WHEN** PR 合入 main 分支
- **THEN** workflow SHALL 建置 image 並僅推 `release` 與 `sha-<short>` 兩個 tag

#### Scenario: workflow 失敗不影響使用者

- **WHEN** release workflow 執行失敗
- **THEN** 既有已發布 image 與既有部署 SHALL 不受影響，repo 主分支保持可繼續 PR

### Requirement: 多 tag 標記策略

對於 git tag `vX.Y.Z` 觸發的 build，workflow SHALL 同時推送下列 tag：`vX.Y.Z`、`vX.Y`、`vX`、`release`、`sha-<short>`。對於 main 分支 push，SHALL 僅推 `release` 與 `sha-<short>`。Tag 命名 SHALL 不使用 `latest`（避免與 docker 慣例混淆）。

#### Scenario: 精確版本 tag 不可被覆蓋

- **WHEN** 已發布 `v0.1.0`，後續又 push `v0.1.0`
- **THEN** workflow SHALL 偵測 tag 已存在並 fail-fast（透過 `docker manifest inspect` 預檢），避免靜默覆蓋

#### Scenario: floating tag 自動遞進

- **WHEN** 發布 `v0.1.5` 後再發布 `v0.1.6`
- **THEN** `v0.1`、`v0`、`release` 三個 floating tag SHALL 全部指向 `v0.1.6`

### Requirement: 多架構 image 建置

對於 git tag 觸發的 build，workflow SHALL 同時建置 `linux/amd64` 與 `linux/arm64` 兩個架構並推送 multi-arch manifest。對於 main 分支 push，SHALL 僅建 `linux/amd64`（縮短 CI 時間）。

#### Scenario: Apple Silicon 可直接 pull arm64

- **WHEN** 使用者於 Mac M 系列執行 `docker compose pull`，且 `.env` 指定 `CCAS_VERSION=v0.1.0`
- **THEN** docker SHALL 自動拉取 `linux/arm64` variant，無需 emulation

#### Scenario: amd64-only fallback

- **WHEN** 使用者於 amd64 機器拉取 `release` tag（main 分支建出）
- **THEN** docker SHALL 拉取 `linux/amd64` image 並正常啟動

### Requirement: Release artifact 同步上傳

當 git tag `v*` 觸發 build 完成後，workflow SHALL 將 `docker/docker-compose.yml` 與 `docker/example.env` 附加到對應的 GitHub Release，使用者可不需 clone repo 即下載。

#### Scenario: Release 頁面包含 compose 檔案

- **WHEN** workflow 完成 `v0.1.0` 發布
- **THEN** GitHub `https://github.com/<owner>/ccas/releases/tag/v0.1.0` SHALL 列出 `docker-compose.yml` 與 `example.env` 兩個可下載 asset

#### Scenario: Compose 檔內容與 repo 一致

- **WHEN** 使用者下載 release 的 `docker-compose.yml`
- **THEN** 該檔 SHALL 與該 tag 在 repo `docker/docker-compose.yml` 內容完全一致

### Requirement: GHA build cache 加速

Workflow SHALL 使用 `cache-from: type=gha` 與 `cache-to: type=gha,mode=max` 配置 docker buildx cache，以縮短後續 build 時間。

#### Scenario: 連續 push 命中 cache

- **WHEN** 同一 PR 連續兩次 push（僅修改 README）
- **THEN** 第二次 build SHALL 命中 cache、image build 階段時間 SHALL 顯著縮短（< 30 秒完成 backend image 建置）

### Requirement: 共用 backend image 跨 worker / scheduler / bot

`ccas-backend` image SHALL 同時支援 `uvicorn`（FastAPI server）、`rq worker`、`scheduler` module、Telegram bot 四種啟動命令。compose 檔 SHALL 透過 service-level `command:` 區分用途，**不得**為 worker / scheduler / bot 各別建置獨立 image。

#### Scenario: 同一 image 啟動不同 service

- **WHEN** compose 啟動 backend、worker、scheduler、bot 四個 service
- **THEN** 四者 SHALL 引用同一個 `ghcr.io/<owner>/ccas-backend:${CCAS_VERSION}` image，僅 `command:` 不同

#### Scenario: image 內含所有必要進入點

- **WHEN** 對 `ccas-backend` image 執行 `docker run --rm -it ... bash` 並檢查
- **THEN** image 內 SHALL 含 `uvicorn`、`rq`、`ccas.scheduler`、Telegram bot 所需所有 Python 依賴

### Requirement: Proxy image 管理唯一 ingress

`ccas-proxy` image SHALL 內建 nginx reverse proxy 設定，負責 prod stack 的唯一外部入口。該 image SHALL 將 `/api/*` 轉發至 `backend:8000`，將其他 Web 路徑轉發至 `frontend:8080`，並提供 `/health` liveness endpoint。

#### Scenario: proxy image 可獨立建置

- **WHEN** release workflow 建置 `ccas-proxy`
- **THEN** build context SHALL 包含 `docker/proxy/Dockerfile` 與 `docker/proxy/nginx.conf`，且不需要 backend / frontend source 才能完成建置

#### Scenario: 所有版本 tag 同步套用到 proxy

- **WHEN** 發布 `v0.1.0`
- **THEN** `ccas-proxy` SHALL 與 backend / frontend 一樣推送 `v0.1.0`、`v0.1`、`v0`、`release`、`sha-<short>` tag，確保 `CCAS_VERSION` 可同步 pin 三個 image
