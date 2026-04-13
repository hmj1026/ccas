---
paths:
  - "**/Dockerfile"
  - "**/docker-compose*.yaml"
  - "**/docker-compose*.yml"
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
- **Image naming**: Do NOT use shared `image:` tags across services with different override targets (causes target conflict in dev mode); let Compose auto-deduplicate by context+target
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
- **Base compose = production**：`target: production`；開發模式由 `docker-compose.override.yml` 自動載入切換至 `dev`（bind mount 原始碼、`UVICORN_RELOAD=1`、frontend 改走 Vite dev server 5173）
- **生產部署**：務必以 `docker compose -f docker-compose.yaml up -d` 明確指定 base compose，略過 override
- **Compose 版本需求**：≥ v2.24（override.yml 使用 `!override` YAML tag 取代 ports 清單，舊版會 parse 失敗）
- **個人化客製**：團隊共用 dev 設定請改 `docker-compose.override.yml`；只屬於你個人的調整放 `docker-compose.local.yml`（已 gitignore，可參考 `docker-compose.local.yml.example`）

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

| Volume | Purpose | Mount Point |
|--------|---------|-------------|
| `./backend/data` | SQLite DB, staging files, credentials | `/data` |
| `ccas-redis` | Redis persistence | `/data` (redis container) |

## Conventions

- Do not add `apt-get` or `apk add` packages without strong justification
- Pin tool versions in Dockerfiles for reproducibility (uv tag, corepack)
- Use `.dockerignore` to exclude `.git`, `node_modules`, `__pycache__`, `.env`
- Use BuildKit cache mounts (`--mount=type=cache`) for package managers
