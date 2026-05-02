#!/usr/bin/env bash
# Docker entrypoint for CCAS backend / worker / scheduler / bot.
#
# Order:
#   1. Bootstrap API_TOKEN（D11 三段式：env > secrets 檔 > 自動產生）
#   2. Validate env against /app/.env.example（image-internal SSOT）
#   3. Seed config from image-internal templates if user mount lacks them（D5）
#   4. Apply alembic migration（backend only — gated by CCAS_RUN_MIGRATIONS）
#   5. Seed bank_configs / categories from yaml（backend only）
#   6. exec service command（uvicorn / rq worker / scheduler / bot）
#
# Usage：本腳本作為 backend image 的 ENTRYPOINT；CMD（uvicorn / rq worker / ...）
# 從 docker-compose.yml 的 `command:` 注入。worker / scheduler / bot 不需跑 migration
# 與 yaml seed，由 SKIP_DB_BOOTSTRAP=1 控制。

set -euo pipefail

# ------------------------------------------------------------------------------
# Resolve script directory（支援 dev bind-mount /scripts 與 prod image /scripts）
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default locations — entrypoint 內部使用；compose 已將 host 路徑掛載到這些 mount point
CCAS_DATA_DIR="${CCAS_DATA_DIR:-/data}"
CCAS_CONFIG_DIR="${BANK_CONFIG_DIR:-/config}"
CCAS_DEFAULT_CONFIG_DIR="${CCAS_DEFAULT_CONFIG_DIR:-/app/default-config}"
SECRETS_DIR="${CCAS_DATA_DIR}/secrets"
API_TOKEN_FILE="${SECRETS_DIR}/api-token"

# ------------------------------------------------------------------------------
# 1. API_TOKEN bootstrap（D11）
# ------------------------------------------------------------------------------
bootstrap_api_token() {
  # (a) env 已設定 → 直接使用，不寫檔
  if [[ -n "${API_TOKEN:-}" ]]; then
    printf '[INFO] 使用 .env / environment 提供的 API_TOKEN\n'
    return 0
  fi

  # (b) secrets 檔已存在 → 讀取載入
  if [[ -f "${API_TOKEN_FILE}" ]]; then
    API_TOKEN="$(<"${API_TOKEN_FILE}")"
    export API_TOKEN
    printf '[INFO] 從 %s 載入既有 API_TOKEN\n' "${API_TOKEN_FILE}"
    return 0
  fi

  # (c) 兩者皆無 → 產生新 token、寫入 secrets/api-token（0600）、export
  if ! mkdir -p "${SECRETS_DIR}"; then
    printf '[ERROR] 無法建立 %s（檢查 ${CCAS_DATA_LOCATION} volume 是否可寫）\n' "${SECRETS_DIR}" >&2
    return 1
  fi

  local new_token
  new_token="$(openssl rand -hex 32)"
  # 先以 0600 建立檔案再寫入，避免短暫 race window
  ( umask 077 && printf '%s' "${new_token}" > "${API_TOKEN_FILE}" )
  chmod 0600 "${API_TOKEN_FILE}"

  API_TOKEN="${new_token}"
  export API_TOKEN
  printf '[INFO] 已自動產生 API_TOKEN，請至 %s 取得（首次啟動）\n' "${API_TOKEN_FILE}"
}

# ------------------------------------------------------------------------------
# 2. 環境變數驗證
# ------------------------------------------------------------------------------
validate_env() {
  # In Docker, env vars are already set via docker-compose env_file.
  # Create an empty file so check-env.sh sources nothing but still
  # validates the process environment against .env.example.
  local tmp_env
  tmp_env="$(mktemp)"
  export ENV_FILE="${tmp_env}"
  export EXAMPLE_FILE="${EXAMPLE_FILE:-/app/.env.example}"

  if [[ -f "${SCRIPT_DIR}/check-env.sh" && -f "${EXAMPLE_FILE}" ]]; then
    printf '==> 驗證環境變數\n'
    "${SCRIPT_DIR}/check-env.sh" || {
      printf '[ERROR] 環境變數驗證失敗。請檢查 docker-compose.yaml 的 env_file 或 environment 設定。\n' >&2
      rm -f "${tmp_env}"
      exit 1
    }
  fi
  rm -f "${tmp_env}"
}

# ------------------------------------------------------------------------------
# 3. Config seed（D5）
# ------------------------------------------------------------------------------
seed_config_file() {
  local file_name="$1"
  local target="${CCAS_CONFIG_DIR}/${file_name}"
  local template="${CCAS_DEFAULT_CONFIG_DIR}/${file_name%.yaml}.example.yaml"

  if [[ -f "${target}" ]]; then
    return 0
  fi

  if [[ ! -f "${template}" ]]; then
    printf '[ERROR] 既找不到 %s，也找不到 image 內建範本 %s\n' "${target}" "${template}" >&2
    printf '[ERROR] 請確認 image 是否完整或 ${CCAS_CONFIG_LOCATION} volume 是否正確掛載\n' >&2
    return 1
  fi

  if ! mkdir -p "${CCAS_CONFIG_DIR}" 2>/dev/null; then
    printf '[ERROR] 無法建立 %s（檢查 ${CCAS_CONFIG_LOCATION} volume 是否可寫）\n' "${CCAS_CONFIG_DIR}" >&2
    return 1
  fi

  cp "${template}" "${target}"
  printf '[WARN] %s 不存在，已從 image 範本複製預設值；如需自訂請編輯 ${CCAS_CONFIG_LOCATION}/%s\n' \
    "${target}" "${file_name}"
}

seed_configs() {
  printf '==> Seed default config templates（如 ${CCAS_CONFIG_LOCATION} 缺檔）\n'
  seed_config_file "banks.yaml"
  seed_config_file "bank-code-registry.yaml"
  seed_config_file "categories.yaml"
}

# ------------------------------------------------------------------------------
# 4 / 5. DB bootstrap（backend only）
# ------------------------------------------------------------------------------
db_bootstrap() {
  printf '==> 套用資料庫 migration\n'
  uv run alembic upgrade head

  printf '==> Seed bank_configs from %s\n' "${CCAS_CONFIG_DIR}"
  if ! uv run python -m ccas.tools.bank_configs --apply; then
    printf '[ERROR] bank_configs seed failed (see stderr above)。\n' >&2
    printf '[ERROR] 請檢查 %s/banks.yaml 與 %s/bank-code-registry.yaml 是否存在且格式正確。\n' \
      "${CCAS_CONFIG_DIR}" "${CCAS_CONFIG_DIR}" >&2
    exit 1
  fi

  printf '==> Seed categories from %s\n' "${CCAS_CONFIG_DIR}"
  if ! uv run python -m ccas.tools.categories --apply; then
    printf '[ERROR] categories seed failed (see stderr above)。\n' >&2
    printf '[ERROR] 請檢查 %s/categories.yaml 是否存在且格式正確。\n' "${CCAS_CONFIG_DIR}" >&2
    exit 1
  fi
}

# ------------------------------------------------------------------------------
# OCR 可用性檢查
# ------------------------------------------------------------------------------
check_ocr() {
  printf '==> 檢查 OCR 可用性\n'
  if command -v tesseract >/dev/null 2>&1; then
    printf '[INFO] tesseract OCR 已安裝: %s\n' "$(tesseract --version 2>&1 | head -1)"
  else
    printf '[WARNING] tesseract OCR 未安裝。商戶名稱 OCR 功能將停用。\n' >&2
    printf '[WARNING] 安裝方式: apt-get install tesseract-ocr tesseract-ocr-chi-tra\n' >&2
  fi
}

# ------------------------------------------------------------------------------
# Main flow
# ------------------------------------------------------------------------------
# 當以 `source` 載入（例如測試）時不執行 main flow，僅暴露上述函式。
# Bash 不在 sourced 模式下提供穩定的「腳本路徑 == $0」判斷，使用 BASH_SOURCE 對比。
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  return 0 2>/dev/null || true
fi

bootstrap_api_token
validate_env
check_ocr
seed_configs

# backend 之外的 service（worker / scheduler / bot）不跑 alembic / yaml seed；
# 由 docker-compose.yml 對對應 service 設 `SKIP_DB_BOOTSTRAP=1` 決定。
if [[ "${SKIP_DB_BOOTSTRAP:-0}" != "1" ]]; then
  db_bootstrap
fi

# ------------------------------------------------------------------------------
# Exec service command
# ------------------------------------------------------------------------------
# 對 backend 而言：CMD 為 uvicorn ...；UVICORN_RELOAD=1 由 dev override 注入。
# 對其他 service：CMD 由 docker-compose.yml 各自指定（rq worker / scheduler / bot）。
if [[ "$#" -gt 0 ]]; then
  # CMD 已透過 ENTRYPOINT/CMD 機制傳入 "$@"
  reload_flag=()
  if [[ -n "${UVICORN_RELOAD:-}" && "$1" == "uv" && "$2" == "run" && "$3" == "uvicorn" ]]; then
    reload_flag=(--reload)
    exec "$@" "${reload_flag[@]}"
  fi
  exec "$@"
fi

# Fallback：未指定 CMD（不應發生）→ 啟動預設 uvicorn
printf '==> 啟動後端 API（fallback default CMD）\n'
reload_flag=()
[[ -n "${UVICORN_RELOAD:-}" ]] && reload_flag=(--reload)
exec uv run uvicorn ccas.api.app:create_app \
  --host 0.0.0.0 \
  --port 8000 \
  --factory \
  "${reload_flag[@]}"
