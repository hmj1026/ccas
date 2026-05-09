#!/usr/bin/env bash
# Tests for scripts/docker-entrypoint.sh
#
# 涵蓋：
#   - bootstrap_master_key：首次產生（0600）/ 既有檔不覆寫
#   - bootstrap_api_token：env 已設定 / secrets 檔已存在 / 兩者皆無
#   - bootstrap_api_token 冪等性（重複呼叫不變）
#   - bootstrap_api_token 檔案權限 0600
#   - seed_config_file：target 存在 / target 缺 + template 存在 / 兩者皆無
#
# 執行：
#   bash tests/scripts/test_entrypoint.sh
# 任一 case 失敗整體 exit 1。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENTRYPOINT="${ROOT_DIR}/scripts/docker-entrypoint.sh"

# entrypoint 內部呼叫 `uv run python -m ccas.tools.*`；該指令需要 backend
# pyproject.toml 在 cwd 或祖先目錄。在 image 內 cwd = /app 且 ccas package
# 已 install；本機跑測試時手動切到 backend/ 確保 uv 能解析專案。
cd "${ROOT_DIR}/backend"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1" >&2; exit 1; }

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

# 為每個 test case 建立隔離 sandbox：
#   - $SANDBOX/data → 模擬 ${CCAS_DATA_LOCATION}
#   - $SANDBOX/config → 模擬 ${CCAS_CONFIG_LOCATION}
#   - $SANDBOX/default-config → 模擬 image 內建範本
new_sandbox() {
  SANDBOX="$(mktemp -d)"
  export CCAS_DATA_DIR="${SANDBOX}/data"
  export BANK_CONFIG_DIR="${SANDBOX}/config"
  export CCAS_DEFAULT_CONFIG_DIR="${SANDBOX}/default-config"
  /bin/mkdir -p "$CCAS_DATA_DIR" "$BANK_CONFIG_DIR" "$CCAS_DEFAULT_CONFIG_DIR"
  unset API_TOKEN || true
}

cleanup_sandbox() {
  /bin/rm -rf "$SANDBOX"
}

# Source entrypoint functions（不觸發 main flow）
load_entrypoint_functions() {
  # 透過子 shell 確保 sourced 的變數不污染 caller，但 functions 取得需在當前 shell
  # 直接 source；entrypoint 已加 BASH_SOURCE != $0 早退保護
  # shellcheck disable=SC1090
  source "$ENTRYPOINT"
}

# ------------------------------------------------------------------------------
# Test cases
# ------------------------------------------------------------------------------

test_master_key_first_run() {
  new_sandbox
  load_entrypoint_functions

  bootstrap_master_key >/dev/null

  local key_file="${CCAS_DATA_DIR}/secrets/master.key"
  [[ -f "$key_file" ]] || fail "未產生 master.key"
  local size
  size="$(wc -c < "$key_file" | tr -d ' ')"
  # Fernet key = 32 bytes, base64 url-safe encoded → 44 chars (no newline)
  [[ "$size" -eq 44 ]] || fail "master.key 大小應為 44 bytes (Fernet base64 key) (got $size)"

  local perms
  perms="$(stat -c '%a' "$key_file" 2>/dev/null || stat -f '%A' "$key_file")"
  [[ "$perms" == "600" ]] || fail "master.key 權限不是 0600 (got $perms)"

  cleanup_sandbox
  pass "bootstrap_master_key: 首次啟動 → 產生 0600 + 44 bytes Fernet key"
}

test_master_key_idempotent() {
  new_sandbox
  load_entrypoint_functions

  /bin/mkdir -p "${CCAS_DATA_DIR}/secrets"
  printf 'pre-existing-key-must-not-be-overwritten=' > "${CCAS_DATA_DIR}/secrets/master.key"
  /bin/chmod 0600 "${CCAS_DATA_DIR}/secrets/master.key"

  bootstrap_master_key >/dev/null

  local content
  content="$(<"${CCAS_DATA_DIR}/secrets/master.key")"
  [[ "$content" == "pre-existing-key-must-not-be-overwritten=" ]] || \
    fail "既有 master.key 被覆寫 (got '$content')"

  cleanup_sandbox
  pass "bootstrap_master_key: 既有檔 → 不覆寫"
}

test_token_env_already_set() {
  new_sandbox
  load_entrypoint_functions

  export API_TOKEN="user-provided-token-do-not-overwrite"
  bootstrap_api_token >/dev/null

  [[ "$API_TOKEN" == "user-provided-token-do-not-overwrite" ]] || fail "env-set token 被覆蓋"
  [[ ! -f "${CCAS_DATA_DIR}/secrets/api-token" ]] || fail "env-set 不應寫 secrets 檔"
  cleanup_sandbox
  pass "bootstrap_api_token: env 已設定 → 不覆寫、不寫檔"
}

test_token_secrets_file_exists() {
  new_sandbox
  load_entrypoint_functions

  /bin/mkdir -p "${CCAS_DATA_DIR}/secrets"
  printf 'existing-secrets-token' > "${CCAS_DATA_DIR}/secrets/api-token"
  /bin/chmod 0600 "${CCAS_DATA_DIR}/secrets/api-token"

  unset API_TOKEN
  bootstrap_api_token >/dev/null

  [[ "$API_TOKEN" == "existing-secrets-token" ]] || fail "未從 secrets 檔載入既有 token (got '$API_TOKEN')"
  cleanup_sandbox
  pass "bootstrap_api_token: secrets 檔已存在 → 讀取載入"
}

test_token_generate_new() {
  new_sandbox
  load_entrypoint_functions

  unset API_TOKEN
  bootstrap_api_token >/dev/null

  local token_file="${CCAS_DATA_DIR}/secrets/api-token"
  [[ -f "$token_file" ]] || fail "未產生 secrets 檔"
  local file_token
  file_token="$(<"$token_file")"
  [[ "$API_TOKEN" == "$file_token" ]] || fail "env API_TOKEN 與檔案內容不一致"
  [[ "${#API_TOKEN}" -eq 64 ]] || fail "新產生 token 長度應為 64 hex chars (got ${#API_TOKEN})"

  # 檔案權限驗證（0600）
  local perms
  perms="$(stat -c '%a' "$token_file" 2>/dev/null || stat -f '%A' "$token_file")"
  [[ "$perms" == "600" ]] || fail "secrets 檔權限不是 0600 (got $perms)"

  cleanup_sandbox
  pass "bootstrap_api_token: 兩者皆無 → 產生 + 寫 0600 + export"
}

test_token_idempotent() {
  new_sandbox
  load_entrypoint_functions

  unset API_TOKEN
  bootstrap_api_token >/dev/null
  local first_token="$API_TOKEN"

  unset API_TOKEN
  bootstrap_api_token >/dev/null
  local second_token="$API_TOKEN"

  [[ "$first_token" == "$second_token" ]] || fail "重啟後 token 不應改變"
  cleanup_sandbox
  pass "bootstrap_api_token: 冪等（重啟後 token 不變）"
}

test_seed_config_target_exists() {
  new_sandbox
  load_entrypoint_functions

  printf 'banks: []\n' > "${BANK_CONFIG_DIR}/banks.yaml"
  printf 'banks: [{template: true}]\n' > "${CCAS_DEFAULT_CONFIG_DIR}/banks.example.yaml"

  seed_config_file "banks.yaml" >/dev/null

  local content
  content="$(<"${BANK_CONFIG_DIR}/banks.yaml")"
  [[ "$content" == "banks: []" ]] || fail "既有 banks.yaml 被覆寫 (got '$content')"
  cleanup_sandbox
  pass "seed_config_file: target 存在 → 不覆寫"
}

test_seed_config_copy_from_template() {
  new_sandbox
  load_entrypoint_functions

  printf 'banks: [{template: true}]\n' > "${CCAS_DEFAULT_CONFIG_DIR}/banks.example.yaml"

  seed_config_file "banks.yaml" >/dev/null

  [[ -f "${BANK_CONFIG_DIR}/banks.yaml" ]] || fail "未從 template 複製"
  local content
  content="$(<"${BANK_CONFIG_DIR}/banks.yaml")"
  [[ "$content" == "banks: [{template: true}]" ]] || fail "複製後內容不符 (got '$content')"
  cleanup_sandbox
  pass "seed_config_file: target 缺 + template 存在 → 複製"
}

test_seed_config_both_missing() {
  new_sandbox
  load_entrypoint_functions

  # 兩者皆無
  if seed_config_file "banks.yaml" 2>/dev/null; then
    fail "兩者皆無時應 return 1"
  fi
  cleanup_sandbox
  pass "seed_config_file: 兩者皆無 → fail-fast"
}

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
test_master_key_first_run
test_master_key_idempotent
test_token_env_already_set
test_token_secrets_file_exists
test_token_generate_new
test_token_idempotent
test_seed_config_target_exists
test_seed_config_copy_from_template
test_seed_config_both_missing

printf "\n${GREEN}All entrypoint tests passed.${NC}\n"
