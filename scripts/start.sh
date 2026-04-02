#!/usr/bin/env bash
# One-click startup: backend (uvicorn) + frontend (vite dev).
# Ctrl+C stops both services.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$ROOT_DIR/.env"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

BACKEND_PID=""
FRONTEND_PID=""

fail() {
  printf '\n[ERROR] %s\n' "$1" >&2
  exit 1
}

step() {
  printf '\n==> %s\n' "$1"
}

cleanup() {
  printf '\n==> 正在停止服務...\n'
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  printf '[OK] 所有服務已停止\n'
}

trap cleanup EXIT INT TERM

# --- Env validation ---
step "驗證環境變數"
"$ROOT_DIR/scripts/check-env.sh" || fail "環境變數驗證失敗，請補齊 .env 後重試。"

[[ -f "$ENV_FILE" ]] || fail "找不到 $ENV_FILE。請先執行 ./scripts/setup.sh"

# Source env
set -a
source "$ENV_FILE"
set +a

# --- Backend setup ---
cd "$BACKEND_DIR"

step "確認後端依賴"
UV_CACHE_DIR="$UV_CACHE_DIR" uv sync

step "套用資料庫 migration"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run alembic upgrade head

# --- Start backend (background) ---
step "啟動後端 API (port 8000)"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run uvicorn ccas.api.app:create_app \
  --host 127.0.0.1 \
  --port 8000 \
  --factory \
  --reload &
BACKEND_PID=$!

# --- Start frontend (background) ---
step "啟動前端 (port 5173)"
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!

# --- Health check ---
step "等待服務就緒..."
HEALTH_TIMEOUT=30
HEALTH_START=$(date +%s)
backend_ready=false
frontend_ready=false

while true; do
  elapsed=$(( $(date +%s) - HEALTH_START ))
  if [[ $elapsed -ge $HEALTH_TIMEOUT ]]; then
    break
  fi

  if [[ "$backend_ready" == "false" ]]; then
    if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
      backend_ready=true
    fi
  fi

  if [[ "$frontend_ready" == "false" ]]; then
    if curl -sf http://localhost:5173 > /dev/null 2>&1; then
      frontend_ready=true
    fi
  fi

  if [[ "$backend_ready" == "true" && "$frontend_ready" == "true" ]]; then
    break
  fi

  sleep 1
done

if [[ "$backend_ready" == "true" && "$frontend_ready" == "true" ]]; then
  printf '\n[OK] 服務就緒\n'
  printf '  Backend:  http://127.0.0.1:8000\n'
  printf '  Frontend: http://localhost:5173\n'
  printf '  按 Ctrl+C 停止所有服務\n'
else
  printf '\n[WARN] 部分服務未在 %d 秒內就緒：\n' "$HEALTH_TIMEOUT"
  [[ "$backend_ready" == "false" ]] && printf '  - Backend (http://127.0.0.1:8000/health) 未回應\n'
  [[ "$frontend_ready" == "false" ]] && printf '  - Frontend (http://localhost:5173) 未回應\n'
  printf '服務仍在運行中，請手動確認。\n'
fi

# Wait for either process to exit
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
