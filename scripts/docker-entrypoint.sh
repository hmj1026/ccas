#!/usr/bin/env bash
# Docker entrypoint for CCAS backend.
# Runs env validation, applies migrations, then starts uvicorn.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# In Docker, env vars are already set via docker-compose env_file.
# We source /dev/null so check-env.sh skips .env sourcing but still checks
# the process environment against .env.example.
export ENV_FILE="/dev/null"
export EXAMPLE_FILE="/app/.env.example"

if [[ -f "$SCRIPT_DIR/check-env.sh" && -f "$EXAMPLE_FILE" ]]; then
  printf '==> 驗證環境變數\n'
  "$SCRIPT_DIR/check-env.sh" || {
    printf '[ERROR] 環境變數驗證失敗。請檢查 docker-compose.yaml 的 env_file 或 environment 設定。\n' >&2
    exit 1
  }
fi

printf '==> 套用資料庫 migration\n'
uv run alembic upgrade head

printf '==> 啟動後端 API\n'
exec uv run uvicorn ccas.api.app:create_app \
  --host 0.0.0.0 \
  --port 8000 \
  --factory
