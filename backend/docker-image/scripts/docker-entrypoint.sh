#!/usr/bin/env bash
# Docker entrypoint for CCAS backend / worker / scheduler / bot.
#
# Order:
#   0. Bootstrap master.key（Fernet 對稱加密；oauth-onboarding-ui §1.2）
#   1. Bootstrap API_TOKEN（D11 三段式：env > secrets 檔 > 自動產生）
#   2. Validate env against /app/.env.example（image-internal SSOT）
#   3. Seed config from image-internal templates if user mount lacks them（D5）
#   4. Apply alembic migration（backend only — gated by CCAS_RUN_MIGRATIONS）
#   5. Seed bank_configs / categories from yaml（backend only）
#   6. Seed bank_settings from banks.yaml（oauth-onboarding-ui §2.6；backend only）
#   7. exec service command（uvicorn / rq worker / scheduler / bot）
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
API_TOKEN_VERSION_FILE="${SECRETS_DIR}/api-token-version"
MASTER_KEY_FILE="${SECRETS_DIR}/master.key"

# ------------------------------------------------------------------------------
# 0. master.key bootstrap（oauth-onboarding-ui §1.2）
# ------------------------------------------------------------------------------
# Fernet 對稱加密金鑰；用於 bank_secrets / Gmail token 之類的密文欄位。
# 三段式（與 API_TOKEN 一致）：env > secrets 檔 > 自動產生。
# 不可外洩、不可遺失：遺失後既有 ciphertext 將永久無法解密，需從備份還原
# ${CCAS_DATA_LOCATION} 整個目錄。
#
# 委派給 ``ccas.storage.secrets.MasterKeyManager.load_or_create``：
# - 該實作以 ``os.open(..., O_EXCL, 0o600)`` 寫檔，避免 race 條件
# - 不經 stdout，key bytes 不會出現在 ``/proc/<pid>/fd/1`` 視窗內
# - 與 backend service 啟動後的解密路徑共用同一個產生邏輯，避免 base64 / 二進位
#   格式偏差
bootstrap_master_key() {
  if [[ -f "${MASTER_KEY_FILE}" ]]; then
    return 0
  fi

  if ! mkdir -p "${SECRETS_DIR}"; then
    printf '[ERROR] 無法建立 %s（檢查 ${CCAS_DATA_LOCATION} volume 是否可寫）\n' "${SECRETS_DIR}" >&2
    return 1
  fi

  uv run python -c "
import sys
from pathlib import Path
from ccas.storage.secrets import MasterKeyManager
MasterKeyManager(Path(sys.argv[1])).load_or_create()
" "${MASTER_KEY_FILE}"
  printf '[INFO] 已自動產生 master.key 於 %s（首次啟動，請務必納入 ${CCAS_DATA_LOCATION} 備份）\n' "${MASTER_KEY_FILE}"
}

# ------------------------------------------------------------------------------
# 1. API_TOKEN bootstrap（D11）
# ------------------------------------------------------------------------------
bootstrap_api_token() {
  # (a) env 已設定 → 直接使用，不寫檔
  if [[ -n "${API_TOKEN:-}" ]]; then
    printf '[INFO] 使用 .env / environment 提供的 API_TOKEN\n'
    # 弱 token 警告（不阻擋啟動）：自動產生路徑為 64 hex chars，env 提供時建議至少 32 字元
    if (( ${#API_TOKEN} < 32 )); then
      printf '[WARN] API_TOKEN 長度僅 %d 字元（< 32），易被暴力猜測；建議改用 `openssl rand -hex 32` 產生的強 token\n' \
        "${#API_TOKEN}" >&2
    fi
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
# 1b. API token 版本檔（oauth-onboarding-ui §6.3）
# ------------------------------------------------------------------------------
# 由 rotate API 在每次 rotate 時 +1；entrypoint 僅負責「首次部署寫入 1」。
# 缺檔時 backend ``current_api_token_version()`` fallback 為 1，因此既有部署
# 升級到含本檔的版本不會破壞行為，但會在第一次 rotate 後有檔。
bootstrap_api_token_version() {
  if [[ -f "${API_TOKEN_VERSION_FILE}" ]]; then
    return 0
  fi

  if ! mkdir -p "${SECRETS_DIR}"; then
    printf '[ERROR] 無法建立 %s（檢查 ${CCAS_DATA_LOCATION} volume 是否可寫）\n' "${SECRETS_DIR}" >&2
    return 1
  fi

  ( umask 077 && printf '%s' "1" > "${API_TOKEN_VERSION_FILE}" )
  chmod 0600 "${API_TOKEN_VERSION_FILE}"
  printf '[INFO] 已初始化 API token 版本檔 %s（v1）\n' "${API_TOKEN_VERSION_FILE}"
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

  # bank_settings seed（oauth-onboarding-ui §2.6）：
  # 為 banks.yaml 中每個銀行寫入預設 BankSettings row（enabled=True）。
  # 既有 row 不覆寫，保留使用者透過 /setup/banks UI 做的修改。fail-soft：
  # 不阻擋啟動，避免 seed 異常讓使用者連登入都進不去。
  printf '==> Seed bank_settings from %s\n' "${CCAS_CONFIG_DIR}"
  if ! uv run python -m ccas.tools.seed_bank_settings; then
    printf '[WARN] bank_settings seed 失敗，可至 /setup/banks 手動補；不阻擋啟動。\n' >&2
  fi

  # gmail_oauth_state 清理（oauth-onboarding-ui §3.8）：
  # 清掉 24 小時以上未使用的 OAuth state row，避免堆積。一次性查詢，
  # 即便 router 端因 callback 流程已自動刪除多數 state，啟動時做總體清掃。
  printf '==> 清理 gmail_oauth_state 過期條目\n'
  if ! uv run python -m ccas.tools.cleanup_gmail_state; then
    printf '[WARN] gmail_oauth_state 清理失敗（不阻擋啟動）。\n' >&2
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

bootstrap_master_key
bootstrap_api_token
bootstrap_api_token_version
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
