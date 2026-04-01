#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$ROOT_DIR/.env"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

fail() {
  printf '\n[ERROR] %s\n' "$1" >&2
  exit 1
}

step() {
  printf '\n==> %s\n' "$1"
}

[[ -f "$ENV_FILE" ]] || fail "找不到 $ENV_FILE。請先執行 ./scripts/setup.sh"

cd "$BACKEND_DIR"

set -a
source "$ENV_FILE"
set +a

[[ -n "${API_TOKEN:-}" ]] || fail "缺少 API_TOKEN。請先補齊 .env 後重試。"

step "確認依賴"
UV_CACHE_DIR="$UV_CACHE_DIR" uv sync

step "套用資料庫 migration"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run alembic upgrade head

step "啟動後端 API"
exec env UV_CACHE_DIR="$UV_CACHE_DIR" uv run uvicorn ccas.api.app:create_app \
  --host 127.0.0.1 \
  --port 8000 \
  --factory \
  --reload
