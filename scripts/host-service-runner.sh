#!/usr/bin/env bash
# Run one CCAS background service from a host service manager.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'usage: %s <worker|scheduler|api|mcp-http> <absolute-path-to-uv>\n' "$0" >&2
  exit 2
fi

SERVICE="$1"
UV_BIN="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

if [[ ! -x "$UV_BIN" ]]; then
  printf 'uv executable is not available: %s\n' "$UV_BIN" >&2
  exit 1
fi

cd "$BACKEND_DIR"

case "$SERVICE" in
  worker)
    REDIS_URL="$("$UV_BIN" run --no-sync python -c \
      'from ccas.config import get_settings; print(get_settings().redis_url)')"
    exec "$UV_BIN" run --no-sync rq worker --url "$REDIS_URL"
    ;;
  scheduler)
    exec "$UV_BIN" run --no-sync python -m ccas.scheduler
    ;;
  api)
    exec "$UV_BIN" run --no-sync uvicorn ccas.api.app:create_app \
      --factory --host 127.0.0.1 --port 8000
    ;;
  mcp-http)
    MCP_HTTP_PORT="$("$UV_BIN" run --no-sync python -c \
      'from ccas.config import get_settings; print(get_settings().mcp_http_port)')"
    exec "$UV_BIN" run --no-sync uvicorn ccas.mcp.http:create_http_app \
      --factory --host 127.0.0.1 --port "$MCP_HTTP_PORT"
    ;;
  *)
    printf 'unknown service: %s\n' "$SERVICE" >&2
    exit 2
    ;;
esac
