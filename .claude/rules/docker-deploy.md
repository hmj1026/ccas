---
paths:
  - "**/Dockerfile"
  - "**/docker-compose*.yaml"
  - "scripts/**"
---
# CCAS Docker & Deployment Conventions

## Docker Images

- **Multi-stage builds**: builder → dev → production (3 stages)
- **Non-root user**: Production images run as `appuser` (UID 1001)
- **Healthchecks**: Every service must define a `HEALTHCHECK` or `healthcheck:`
- **Base images**: Python 3.12-slim (backend), node:22-slim (frontend build), nginx:alpine (frontend serve)

## Docker Compose

- **Services**: backend, worker, scheduler, bot, redis
- **Shared env**: Use `x-shared-env` anchor for common environment variables
- **Ports**: Bind to `127.0.0.1` only (not `0.0.0.0`) for local dev security
- **Volumes**: Named volumes for persistent data (`ccas-data`, `ccas-redis`)
- **Health checks**: Required for backend and redis; other services depend on healthy state

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

- `scripts/docker-entrypoint.sh`: Validates env → runs migrations → starts server
- Always check required env vars before proceeding
- Run `alembic upgrade head` before starting the application
- Use `exec` for the final command to properly handle signals

## Volume Mounts

| Volume | Purpose | Mount Point |
|--------|---------|-------------|
| `ccas-data` | SQLite DB, staging files, credentials | `/data` |
| `ccas-redis` | Redis persistence | `/data` (redis container) |

## Conventions

- Do not add `apt-get` or `apk add` packages without strong justification
- Pin package versions in Dockerfiles for reproducibility
- Use `.dockerignore` to exclude `.git`, `node_modules`, `__pycache__`, `.env`
