#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ENV_FILE="$ROOT_DIR/.env"
BANKS_FILE="$ROOT_DIR/config/banks.yaml"
BANKS_EXAMPLE_FILE="$ROOT_DIR/config/banks.example.yaml"
REGISTRY_FILE="$ROOT_DIR/config/bank-code-registry.yaml"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

step() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf '\n[ERROR] %s\n' "$1" >&2
  exit 1
}

require_file() {
  local file_path="$1"
  local fix_message="$2"
  [[ -f "$file_path" ]] || fail "$fix_message"
}

require_env() {
  local var_name="$1"
  local fix_message="$2"
  [[ -n "${!var_name:-}" ]] || fail "$fix_message"
}

require_file "$ENV_FILE" "找不到 $ENV_FILE。請先執行: cp .env.example .env"
require_file "$REGISTRY_FILE" "找不到 $REGISTRY_FILE。請確認 repo 內容完整。"

if [[ ! -f "$BANKS_FILE" ]]; then
  cp "$BANKS_EXAMPLE_FILE" "$BANKS_FILE"
  fail "已建立 $BANKS_FILE。請先編輯這個檔案，再重新執行 ./scripts/setup.sh"
fi

cd "$BACKEND_DIR"

set -a
source "$ENV_FILE"
set +a

require_env "API_TOKEN" "缺少 API_TOKEN。請編輯 $ENV_FILE 後重試。"
require_env "TELEGRAM_BOT_TOKEN" "缺少 TELEGRAM_BOT_TOKEN。請先向 BotFather 申請 token，再編輯 $ENV_FILE。"
require_env "TELEGRAM_CHAT_ID" "缺少 TELEGRAM_CHAT_ID。請先對 bot 傳訊息並用 getUpdates 查出 chat id，再編輯 $ENV_FILE。"
require_env "TELEGRAM_ALLOWED_CHAT_IDS" "缺少 TELEGRAM_ALLOWED_CHAT_IDS。請至少填入和 TELEGRAM_CHAT_ID 相同的值。"
require_env "GMAIL_CREDENTIALS_PATH" "缺少 GMAIL_CREDENTIALS_PATH。請編輯 $ENV_FILE 後重試。"
require_env "GMAIL_TOKEN_PATH" "缺少 GMAIL_TOKEN_PATH。請編輯 $ENV_FILE 後重試。"
require_env "STAGING_DIR" "缺少 STAGING_DIR。請編輯 $ENV_FILE 後重試。"

require_file "$GMAIL_CREDENTIALS_PATH" "找不到 credentials.json：$GMAIL_CREDENTIALS_PATH。請把 Google Cloud 下載的 OAuth 憑證放到這個路徑，或修改 .env 的 GMAIL_CREDENTIALS_PATH。"

mkdir -p "$(dirname "$GMAIL_TOKEN_PATH")" "$STAGING_DIR"

step "安裝後端依賴"
UV_CACHE_DIR="$UV_CACHE_DIR" uv sync

step "產生或確認 Gmail token"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run python -m ccas.tools.gmail_auth

step "套用資料庫 migration"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run alembic upgrade head

step "預覽 bank configs 同步內容"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run python -m ccas.tools.bank_configs \
  --config ../config/banks.yaml \
  --registry ../config/bank-code-registry.yaml

step "寫入 bank configs 到資料庫"
UV_CACHE_DIR="$UV_CACHE_DIR" uv run python -m ccas.tools.bank_configs \
  --config ../config/banks.yaml \
  --registry ../config/bank-code-registry.yaml \
  --apply

printf '\n[OK] 初始化完成。\n'
printf '下一步：執行 ./scripts/start.sh 啟動後端。\n'
