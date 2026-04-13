#!/usr/bin/env bash
# Docker entrypoint for CCAS backend.
# Runs env validation, applies migrations, then starts uvicorn.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# In Docker, env vars are already set via docker-compose env_file.
# Create an empty file so check-env.sh sources nothing but still
# validates the process environment against .env.example.
ENV_FILE="$(mktemp)"
export ENV_FILE
export EXAMPLE_FILE="/app/.env.example"

if [[ -f "$SCRIPT_DIR/check-env.sh" && -f "$EXAMPLE_FILE" ]]; then
  printf '==> 驗證環境變數\n'
  "$SCRIPT_DIR/check-env.sh" || {
    printf '[ERROR] 環境變數驗證失敗。請檢查 docker-compose.yaml 的 env_file 或 environment 設定。\n' >&2
    exit 1
  }
fi

printf '==> 檢查 OCR 可用性\n'
if command -v tesseract >/dev/null 2>&1; then
  printf '[INFO] tesseract OCR 已安裝: %s\n' "$(tesseract --version 2>&1 | head -1)"
else
  printf '[WARNING] tesseract OCR 未安裝。商戶名稱 OCR 功能將停用。\n' >&2
  printf '[WARNING] 安裝方式: apt-get install tesseract-ocr tesseract-ocr-chi-tra\n' >&2
fi

printf '==> 套用資料庫 migration\n'
uv run alembic upgrade head

printf '==> Seed bank_configs from %s\n' "${BANK_CONFIG_DIR:-/config}"
if ! uv run python -m ccas.tools.bank_configs --apply; then
  printf '[ERROR] bank_configs seed failed (see stderr above)。\n' >&2
  printf '[ERROR] 請檢查 %s/banks.yaml 與 %s/bank-code-registry.yaml 是否存在且格式正確。\n' \
    "${BANK_CONFIG_DIR:-/config}" "${BANK_CONFIG_DIR:-/config}" >&2
  exit 1
fi

printf '==> Seed categories from %s\n' "${BANK_CONFIG_DIR:-/config}"
if ! uv run python -m ccas.tools.categories --apply; then
  printf '[ERROR] categories seed failed (see stderr above)。\n' >&2
  printf '[ERROR] 請檢查 %s/categories.yaml 是否存在且格式正確。\n' \
    "${BANK_CONFIG_DIR:-/config}" >&2
  exit 1
fi

printf '==> 啟動後端 API\n'
# UVICORN_RELOAD=1 由 docker-compose.override.yml 注入，啟用 hot reload；
# 生產環境未設定此變數，reload_flag 保持空陣列。
reload_flag=()
[[ -n "${UVICORN_RELOAD:-}" ]] && reload_flag=(--reload)
exec uv run uvicorn ccas.api.app:create_app \
  --host 0.0.0.0 \
  --port 8000 \
  --factory \
  "${reload_flag[@]}"
