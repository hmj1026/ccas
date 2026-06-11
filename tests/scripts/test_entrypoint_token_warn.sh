#!/usr/bin/env bash
# Tests for scripts/docker-entrypoint.sh — API_TOKEN 長度警告（login-rate-limit P1）
#
# 涵蓋：
#   - bootstrap_api_token：env 提供且 < 32 字元 → stderr 出現 [WARN]、不中止
#   - bootstrap_api_token：env 提供且 >= 32 字元 → 無警告
#
# 執行：
#   bash tests/scripts/test_entrypoint_token_warn.sh
# 任一 case 失敗整體 exit 1。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENTRYPOINT="${ROOT_DIR}/scripts/docker-entrypoint.sh"

cd "${ROOT_DIR}/backend"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1" >&2; exit 1; }

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

load_entrypoint_functions() {
  # shellcheck disable=SC1090
  source "$ENTRYPOINT"
}

test_token_env_short_warns() {
  new_sandbox
  load_entrypoint_functions

  export API_TOKEN="short-token-16ch"  # 16 chars < 32
  local stderr_out
  stderr_out="$(bootstrap_api_token 2>&1 >/dev/null)" || fail "短 token 不應導致非零 exit（warn only）"

  [[ "$stderr_out" == *"[WARN]"* ]] || fail "短 token 應在 stderr 輸出 [WARN] (got '$stderr_out')"
  [[ "$API_TOKEN" == "short-token-16ch" ]] || fail "env-set token 被覆蓋"
  [[ ! -f "${CCAS_DATA_DIR}/secrets/api-token" ]] || fail "env-set 不應寫 secrets 檔"
  cleanup_sandbox
  pass "bootstrap_api_token: env token < 32 字元 → stderr [WARN]、不中止"
}

test_token_env_long_no_warn() {
  new_sandbox
  load_entrypoint_functions

  export API_TOKEN="$(printf 'a%.0s' {1..32})"  # exactly 32 chars
  local stderr_out
  stderr_out="$(bootstrap_api_token 2>&1 >/dev/null)" || fail "合規 token 不應導致非零 exit"

  [[ "$stderr_out" != *"[WARN]"* ]] || fail ">= 32 字元 token 不應警告 (got '$stderr_out')"
  cleanup_sandbox
  pass "bootstrap_api_token: env token >= 32 字元 → 無警告"
}

test_token_env_short_warns
test_token_env_long_no_warn

printf "\n${GREEN}All entrypoint token-warn tests passed.${NC}\n"
