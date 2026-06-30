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
  - **dev compose** (root `docker-compose.yaml`): do NOT use shared `image:` tags across services with different override targets (causes target conflict in dev mode); let Compose auto-deduplicate by context+target
  - **prod compose** (`docker/docker-compose.yml`): all services pull GHCR release images: `ghcr.io/${REPO_OWNER}/ccas-backend:${CCAS_VERSION:-release}`, `ccas-frontend`, `ccas-proxy`. backend / worker / scheduler / bot share `ccas-backend` image, differ only in `command:`
- **OCI labels**: Production stages must include `org.opencontainers.image.title` and `description`

## Docker Compose

- **Services**: backend, worker, scheduler, bot, frontend, redis
- **Shared env**: Use `x-shared-env` anchor for common environment variables
- **Ports**: Bind to `127.0.0.1` only (not `0.0.0.0`) for local dev security
- **Frontend port**: 8080 (production nginx, non-root); 5173 (dev Vite, via override)
- **Volumes**: Named volumes for persistent data (`ccas-redis`)
- **Health checks**: Required for backend and redis; other services depend on healthy state
- **stop_grace_period**: worker 30s, backend 15s, scheduler/bot 10s
- **Redis**: `--maxmemory ${REDIS_MAXMEMORY:-256mb} --maxmemory-policy ${REDIS_MAXMEMORY_POLICY:-allkeys-lru} --appendonly yes` (overrideable via `.env`)
- **Startup paths (dev / prod split)**:
  - **dev**: root `docker-compose.yaml` (with `build:`, target `production`) + `docker-compose.override.yml` (auto-loaded: switches to `dev` target, bind-mounts source, `UVICORN_RELOAD=1`, frontend uses Vite dev server at 5173). Command: `docker compose up -d`
  - **prod (pull-only, release)**: `docker/docker-compose.yml` (pure `image:`, no `build:`, pulls from GHCR), only `proxy` service exposes external port. Command: `docker compose -f docker/docker-compose.yml pull && docker compose -f docker/docker-compose.yml up -d`
- **Local production image verification**: when you need to test prod compose with a locally built image: `docker build --target production -t ghcr.io/<owner>/ccas-backend:local backend/` (same for frontend/proxy), then `CCAS_VERSION=local REPO_OWNER=<owner> docker compose -f docker/docker-compose.yml up -d`. Do NOT skip the override on root `docker-compose.yaml` to simulate prod (deprecated approach)
- **Compose version requirement**: ≥ v2.24 (override.yml uses `!override` YAML tag to replace port lists; older versions will fail to parse)
- **Personal customization**: shared dev settings go in `docker-compose.override.yml`; personal-only adjustments go in `docker-compose.local.yml` (gitignored; see `docker-compose.local.yml.example`)
- **Prod compose iron laws**:
  - All CCAS-managed services must use `image:`, never `build:`
  - Only `proxy` service exposes `${CCAS_PORT:-8080}:8080` to host; all others declare no host `ports:`
  - Host volume paths use `${CCAS_DATA_LOCATION:-./data}` / `${CCAS_CONFIG_LOCATION:-./config}` / `${CCAS_LOG_LOCATION:-./logs}` for user customization
  - Redis uses bind mount `${CCAS_DATA_LOCATION:-./data}/redis:/data` (not named volume), fulfilling "backup single data directory" promise
  - bot service does not use `profiles`; handle missing token with disabled idle, not crashloop

## Environment Variables

- **Never hardcode** secrets, tokens, or passwords in Dockerfiles or compose files
- Use `env_file: ./.env` in compose for injection
- Docker overrides (e.g., `DATABASE_URL` with `/data/` prefix) go in `x-shared-env`
- Local dev defaults in `.env.example` use relative paths (`./data/...`)

## Scripts

- All `scripts/*.sh` must `chmod +x` and start with `set -euo pipefail`. POSIX/bash conventions otherwise standard.

## SSOT Sync (root → backend/docker-image/)

The backend image production stage bakes the following files into the image via `backend/` build context, so the repo has "SSOT" and "mirror" copies. **Edit only the SSOT**; mirrors are overwritten from SSOT by `scripts/sync-docker-image-assets.sh`.

| SSOT (edit here) | Mirror (do not edit directly) |
|---|---|
| `scripts/docker-entrypoint.sh` | `backend/docker-image/scripts/docker-entrypoint.sh` |
| `scripts/check-env.sh` | `backend/docker-image/scripts/check-env.sh` |
| `.env.example` | `backend/docker-image/.env.example` |
| `config/banks.example.yaml` | `backend/docker-image/default-config/banks.example.yaml` |
| `config/bank-code-registry.example.yaml` | `backend/docker-image/default-config/bank-code-registry.example.yaml` |
| `config/categories.example.yaml` | `backend/docker-image/default-config/categories.example.yaml` |

**`.env` consumers (single file, three layers)**: backend `ccas.config.Settings` (pydantic-settings), frontend Vite dev proxy (vars must use `VITE_` prefix to be exposed), Docker Compose `x-shared-env` anchor. Adding a new env var means updating `.env.example` + `backend/ccas/config.py`; if browser-visible, also prefix `VITE_`.

**Rules**:
- After modifying any SSOT source, run `./scripts/sync-docker-image-assets.sh` **in the same commit** and stage the updated mirrors together
- Never edit `backend/docker-image/scripts/`, `backend/docker-image/default-config/`, or `backend/docker-image/.env.example` directly (these are overwrite targets); to add new sync pairs, edit `FILE_PAIRS` in `scripts/sync-docker-image-assets.sh`
- `docker/example.env` is a subset of `.env.example` (with docker overrides); validated by `scripts/check-env-sync.sh`; changing one requires checking the other
- Local `scripts/pre-push.sh` and CI `Scripts & Env Sync Checks` job both run `--check`; run `./scripts/sync-docker-image-assets.sh --check` and `./scripts/check-env-sync.sh` locally before pushing to avoid CI failures

## Repo-level Process Gates

Four-layer gate responsibility table (any new check must be added to exactly one layer, no duplication):

| Layer | Trigger | Responsibility | Tools / Config |
|---|---|---|---|
| **PostToolUse hooks** | Every Edit/Write | Real-time lint / typecheck / TDD red / SQLAlchemy / Alembic / Docker / frontend lint (**warning layer, non-blocking**) | `.claude/settings.json` + `.claude/hooks/ccas-*.sh` (8 scripts) |
| **`scripts/pre-commit.sh`** (→ `.git/hooks/pre-commit`) | git commit | gitleaks secret scan + `ruff check --fix` + `ruff format` on staged Python + `pyright` + `eslint` on staged TS | `scripts/pre-commit.sh` (versioned SSOT) |
| **`scripts/pre-push.sh`** (→ `.git/hooks/pre-push`) | git push | `verify-claude-plugins.sh` + `check-env-sync.sh` + `sync-docker-image-assets.sh --check` + full repo `ruff check` / `ruff format --check` / `pyright` / `pytest --cov-fail-under=80` + `eslint` / `pnpm build` / `pnpm test --coverage` (vitest) | `scripts/pre-push.sh` (versioned SSOT) |
| **CI** (`.github/workflows/ci.yaml`) | push / PR | Last-resort gate; equivalent to pre-push plus e2e tests | `.github/workflows/ci.yaml` |

**Design principles**:
- pre-push.sh and CI scripts-checks must be **equivalent** (any new check added to both); CI must not be the sole guardian of SSOT drift checks
- PostToolUse = real-time friendly warning, non-blocking; pre-commit = commit-time auto-fix + static check, blocking; pre-push = full quality gate, blocking; CI = last-resort + e2e
- Install local hooks: `./scripts/setup-hooks.sh` (symlinks `scripts/pre-*.sh` into `.git/hooks/`)

## Entrypoint Pattern

- `scripts/docker-entrypoint.sh`: validates env → runs migrations → seeds configs → starts uvicorn
- Always check required env vars before proceeding
- Run `alembic upgrade head` before starting the application
- Use `exec` for the final command to properly handle signals
- **Hot reload**: `UVICORN_RELOAD=1` is injected by `docker-compose.override.yml`; entrypoint appends `--reload` when set; not present in production

## Volume Mounts

**dev compose** (root `docker-compose.yaml`):

| Volume | Purpose | Mount Point |
|--------|---------|-------------|
| `./backend/data` | SQLite DB, staging files, credentials | `/data` |
| `./config` | bank yaml / categories.yaml | `/config:ro` |
| `./logs` | service log file | `/logs` |
| `ccas-redis` | Redis persistence (named volume) | `/data` (redis container) |

**prod compose** (`docker/docker-compose.yml`): all host volumes use `${CCAS_*_LOCATION}` variables; redis uses bind mount; backing up `${CCAS_DATA_LOCATION}` is sufficient to preserve all state:

| Host path | Purpose | Mount Point |
|-----------|---------|-------------|
| `${CCAS_DATA_LOCATION:-./data}` | SQLite DB, staging files, credentials, secrets | `/data` |
| `${CCAS_DATA_LOCATION:-./data}/redis` | Redis persistence (bind mount) | `/data` (redis container) |
| `${CCAS_CONFIG_LOCATION:-./config}` | bank yaml / categories.yaml | `/config` |
| `${CCAS_LOG_LOCATION:-./logs}` | service log file | `/logs` |
