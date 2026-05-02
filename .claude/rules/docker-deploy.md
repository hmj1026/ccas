---
paths:
  - "**/Dockerfile"
  - "**/docker-compose*.yaml"
  - "**/docker-compose*.yml"
  - "docker/**"
  - "scripts/**"
---
# CCAS Docker & Deployment Conventions

## Docker Images

- **Multi-stage builds**: uv (binary source) → builder → dev → production (backend); base → dev → build → production (frontend)
- **Non-root user**: ALL production images run as `appuser` (UID 1001) — both backend and frontend
- **Healthchecks**: Every service must define a `HEALTHCHECK` or `healthcheck:`
- **Base images**: Python 3.12-slim (backend), node:22-slim (frontend build), nginx:alpine (frontend serve)
- **uv binary**: Copied from `ghcr.io/astral-sh/uv:0.10` — never `pip install uv`
- **pnpm**: Via `corepack enable` in Node base stage — never `npm install -g pnpm`
- **Image naming**:
  - **dev compose**（根目錄 `docker-compose.yaml`）：do NOT use shared `image:` tags across services with different override targets (causes target conflict in dev mode); let Compose auto-deduplicate by context+target
  - **prod compose**（`docker/docker-compose.yml`）：所有 service 拉 GHCR 發布 image：`ghcr.io/${REPO_OWNER}/ccas-backend:${CCAS_VERSION:-release}`、`ghcr.io/${REPO_OWNER}/ccas-frontend:${CCAS_VERSION:-release}`、`ghcr.io/${REPO_OWNER}/ccas-proxy:${CCAS_VERSION:-release}`。backend / worker / scheduler / bot 四個 service 共用 `ccas-backend` image，僅 `command:` 不同
- **OCI labels**: Production stages must include `org.opencontainers.image.title` and `description`

## Docker Compose

- **Services**: backend, worker, scheduler, bot, frontend, redis
- **Shared env**: Use `x-shared-env` anchor for common environment variables
- **Ports**: Bind to `127.0.0.1` only (not `0.0.0.0`) for local dev security
- **Frontend port**: 8080 (production nginx, non-root); 5173 (dev Vite, via override)
- **Volumes**: Named volumes for persistent data (`ccas-redis`)
- **Health checks**: Required for backend and redis; other services depend on healthy state
- **stop_grace_period**: worker 30s, backend 15s, scheduler/bot 10s
- **Redis**: `--maxmemory ${REDIS_MAXMEMORY:-256mb} --maxmemory-policy ${REDIS_MAXMEMORY_POLICY:-allkeys-lru} --appendonly yes`（可透過 `.env` 覆寫）
- **Compose 啟動路徑（dev / prod 二分法）**：
  - **dev**：根目錄 `docker-compose.yaml`（含 `build:`，target 為 `production`）+ `docker-compose.override.yml`（自動載入切到 `dev` target、bind mount 原始碼、`UVICORN_RELOAD=1`、frontend 改走 Vite dev server 5173）。指令：`docker compose up -d`
  - **prod（pull-only，發布版）**：`docker/docker-compose.yml`（純 `image:`，無 `build:`，從 GHCR 拉 release image），對外只透過 `proxy` service 單一 port 暴露。指令：`docker compose -f docker/docker-compose.yml pull && docker compose -f docker/docker-compose.yml up -d`
- **本機驗證 production image**：需自建 image 驗證 prod compose 時，先 `docker build --target production -t ghcr.io/<owner>/ccas-backend:local backend/`（frontend / proxy 同理），再以 `CCAS_VERSION=local REPO_OWNER=<owner> docker compose -f docker/docker-compose.yml up -d` 啟動。**不**在根目錄 `docker-compose.yaml` 上跳過 override 來模擬 prod（已棄用的中間路徑）
- **Compose 版本需求**：≥ v2.24（override.yml 使用 `!override` YAML tag 取代 ports 清單，舊版會 parse 失敗）
- **個人化客製**：團隊共用 dev 設定請改 `docker-compose.override.yml`；只屬於你個人的調整放 `docker-compose.local.yml`（已 gitignore，可參考 `docker-compose.local.yml.example`）
- **Prod compose 設計鐵律**：
  - 所有 CCAS-managed service 一律 `image:`，**不得**含 `build:`
  - 僅 `proxy` service 對 host 暴露 `${CCAS_PORT:-8080}:8080`；backend / worker / scheduler / bot / frontend / redis 一律不宣告 host `ports:`
  - host volume 路徑使用 `${CCAS_DATA_LOCATION:-./data}` / `${CCAS_CONFIG_LOCATION:-./config}` / `${CCAS_LOG_LOCATION:-./logs}` 變數，便於使用者自訂位置
  - redis 使用 bind mount `${CCAS_DATA_LOCATION:-./data}/redis:/data`（不再用 named volume），確保「備份單一 data 目錄即足夠」承諾完整
  - bot service 不使用 `profiles`；token 缺值時以 disabled idle 處理、不 crashloop

## Environment Variables

- **Never hardcode** secrets, tokens, or passwords in Dockerfiles or compose files
- Use `env_file: ./.env` in compose for injection
- Docker overrides (e.g., `DATABASE_URL` with `/data/` prefix) go in `x-shared-env`
- Local dev defaults in `.env.example` use relative paths (`./data/...`)

## Scripts

- **Shell scripts**: Must be POSIX-compatible (`#!/bin/bash` or `#!/bin/sh`)
- **Executable bit**: All scripts in `scripts/` must have `chmod +x`
- **Error handling**: Use `set -euo pipefail` at the top of every script
- **Cross-platform**: Use `$(command)` not backticks; use `$HOME` not `~` in scripts

## Entrypoint Pattern

- `scripts/docker-entrypoint.sh`: Validates env → runs migrations → seeds configs → starts uvicorn
- Always check required env vars before proceeding
- Run `alembic upgrade head` before starting the application
- Use `exec` for the final command to properly handle signals
- **Hot reload**：`UVICORN_RELOAD=1` 由 `docker-compose.override.yml` 注入，讓 entrypoint 附加 `--reload`；生產環境不設定此變數

## Volume Mounts

**dev compose**（根目錄 `docker-compose.yaml`）：

| Volume | Purpose | Mount Point |
|--------|---------|-------------|
| `./backend/data` | SQLite DB, staging files, credentials | `/data` |
| `./config` | bank yaml / categories.yaml | `/config:ro` |
| `./logs` | service log file | `/logs` |
| `ccas-redis` | Redis persistence (named volume) | `/data` (redis container) |

**prod compose**（`docker/docker-compose.yml`）：所有 host volume 走 `${CCAS_*_LOCATION}` 變數，redis 改 bind mount，使用者只需備份 `${CCAS_DATA_LOCATION}` 目錄即可保留全部狀態：

| Host path | Purpose | Mount Point |
|-----------|---------|-------------|
| `${CCAS_DATA_LOCATION:-./data}` | SQLite DB, staging files, credentials, secrets | `/data` |
| `${CCAS_DATA_LOCATION:-./data}/redis` | Redis persistence (bind mount) | `/data` (redis container) |
| `${CCAS_CONFIG_LOCATION:-./config}` | bank yaml / categories.yaml | `/config` |
| `${CCAS_LOG_LOCATION:-./logs}` | service log file | `/logs` |

## Conventions

- Do not add `apt-get` or `apk add` packages without strong justification
- Pin tool versions in Dockerfiles for reproducibility (uv tag, corepack)
- Use `.dockerignore` to exclude `.git`, `node_modules`, `__pycache__`, `.env`
- Use BuildKit cache mounts (`--mount=type=cache`) for package managers
