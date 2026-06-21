#!/usr/bin/env bash
# Tests for scripts/check-env.sh
#
# Locks down the spec contract:
#   - .env-explicit empty (KEY=) for CCAS_*_LOCATION / API_TOKEN → rc=1 (§3.3, §3.3.1)
#   - .env not mentioning the key (process env defaulted) → only warning, rc=0
#   - CCAS_VERSION format regex (release / local / vX[.Y[.Z]][-suffix]) (§3.2)
#   - CCAS_PORT range 1-65535 integer (§3.3.1)
#
# Background: path-C round-2 verification mistakenly reported a spec gap because
# the test ENV_FILE was a fresh `mktemp` empty file with the value supplied via
# process env. `is_explicitly_set_in_env_file` greps the file and returns false,
# so the "set but empty" branch is correctly skipped. The actual contract — which
# IS implemented — only triggers when the file *contains* `KEY=`. This regression
# suite captures both legs so future refactors of `is_explicitly_set_in_env_file`
# (or its callers) cannot silently drop one branch without a red test.
#
# Run:
#   bash tests/scripts/test_check_env.sh
# Any case failure exits non-zero.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${ROOT_DIR}/scripts/check-env.sh"
EXAMPLE="${ROOT_DIR}/.env.example"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1" >&2; exit 1; }

# Run check-env.sh against an inline .env body. Returns the script's exit code.
# Captures stdout+stderr to $LAST_OUT for assertions.
LAST_OUT=""
run_check() {
  local env_body="$1"
  local tmp
  tmp=$(mktemp)
  printf '%s' "$env_body" > "$tmp"
  set +e
  LAST_OUT=$(ENV_FILE="$tmp" EXAMPLE_FILE="$EXAMPLE" bash "$SCRIPT" 2>&1)
  local rc=$?
  set -e
  rm -f "$tmp"
  return $rc
}

# Minimal .env body with all CCAS-specific knobs set to known-good values so
# warnings about other optional vars don't drown out the case under test.
BASE_ENV='CCAS_VERSION=local
CCAS_DATA_LOCATION=./data
CCAS_CONFIG_LOCATION=./config
CCAS_LOG_LOCATION=./logs
CCAS_PORT=8080
'

# ------------------------------------------------------------------------------
# Cases
# ------------------------------------------------------------------------------

# 1. baseline: all knobs valid → no errors (only optional warnings tolerated).
run_check "$BASE_ENV" || fail "baseline rc=$? (expected 0); out=$LAST_OUT"
pass "baseline 全 valid → rc=0"

# 2-4. CCAS_*_LOCATION explicitly empty in .env → rc=1
for var in CCAS_DATA_LOCATION CCAS_CONFIG_LOCATION CCAS_LOG_LOCATION; do
  body="${BASE_ENV//${var}=*/${var}=}"  # replace value to empty
  if run_check "$body"; then
    fail "$var='' 應 rc=1，但得 rc=0; out=$LAST_OUT"
  fi
  printf '%s' "$LAST_OUT" | grep -q "$var 已在 .env 設定但為空字串" \
    || fail "$var='' 訊息缺對應字樣; out=$LAST_OUT"
  pass "$var 顯式空字串 → rc=1 + 明確訊息"
done

# 5. CCAS_DATA_LOCATION not mentioned in .env → only warning, rc=0
body="$(printf '%s\n' "$BASE_ENV" | grep -v '^CCAS_DATA_LOCATION=')"
run_check "$body" || fail "CCAS_DATA_LOCATION 缺漏（非顯式空）應 rc=0; out=$LAST_OUT"
printf '%s' "$LAST_OUT" | grep -q "已在 .env 設定但為空字串" \
  && fail "CCAS_DATA_LOCATION 未提及不應觸發顯式空字串錯誤; out=$LAST_OUT" \
  || true
pass "CCAS_DATA_LOCATION 未提及（默認生效）→ rc=0 only warning"

# 6. CCAS_VERSION format invalid → rc=1
body="${BASE_ENV//CCAS_VERSION=local/CCAS_VERSION=foo}"
if run_check "$body"; then
  fail "CCAS_VERSION=foo 應 rc=1; out=$LAST_OUT"
fi
printf '%s' "$LAST_OUT" | grep -q "CCAS_VERSION='foo' 不符合允許格式" \
  || fail "CCAS_VERSION=foo 訊息缺對應字樣; out=$LAST_OUT"
pass "CCAS_VERSION=foo → rc=1 + 格式訊息"

# 7. CCAS_VERSION=v1.0.0 → rc=0
body="${BASE_ENV//CCAS_VERSION=local/CCAS_VERSION=v1.0.0}"
run_check "$body" || fail "CCAS_VERSION=v1.0.0 應 rc=0; out=$LAST_OUT"
pass "CCAS_VERSION=v1.0.0 → rc=0"

# 8. CCAS_VERSION=v0.1.0-rc.1 (suffix variant) → rc=0
body="${BASE_ENV//CCAS_VERSION=local/CCAS_VERSION=v0.1.0-rc.1}"
run_check "$body" || fail "CCAS_VERSION=v0.1.0-rc.1 應 rc=0; out=$LAST_OUT"
pass "CCAS_VERSION=v0.1.0-rc.1 → rc=0"

# 9. CCAS_PORT=0 (out of range) → rc=1
body="${BASE_ENV//CCAS_PORT=8080/CCAS_PORT=0}"
if run_check "$body"; then
  fail "CCAS_PORT=0 應 rc=1; out=$LAST_OUT"
fi
printf '%s' "$LAST_OUT" | grep -q "CCAS_PORT='0' 不是 1-65535" \
  || fail "CCAS_PORT=0 訊息缺對應字樣; out=$LAST_OUT"
pass "CCAS_PORT=0 → rc=1"

# 10. CCAS_PORT=65535 (upper boundary inclusive) → rc=0
body="${BASE_ENV//CCAS_PORT=8080/CCAS_PORT=65535}"
run_check "$body" || fail "CCAS_PORT=65535 應 rc=0; out=$LAST_OUT"
pass "CCAS_PORT=65535 → rc=0 (上界 inclusive)"

# 11. CCAS_PORT=99999 → rc=1
body="${BASE_ENV//CCAS_PORT=8080/CCAS_PORT=99999}"
if run_check "$body"; then
  fail "CCAS_PORT=99999 應 rc=1; out=$LAST_OUT"
fi
pass "CCAS_PORT=99999 → rc=1"

# 12. API_TOKEN= 顯式空 → rc=1
body="${BASE_ENV}API_TOKEN=
"
if run_check "$body"; then
  fail "API_TOKEN= 顯式空應 rc=1; out=$LAST_OUT"
fi
printf '%s' "$LAST_OUT" | grep -q "API_TOKEN 已在 .env 顯式設為空字串" \
  || fail "API_TOKEN= 顯式空訊息缺對應字樣; out=$LAST_OUT"
pass "API_TOKEN= 顯式空字串 → rc=1"

# 13. API_TOKEN 完全未提及 → rc=0 (entrypoint 將自動產生)
run_check "$BASE_ENV" || fail "API_TOKEN 未提及不應 rc!=0; out=$LAST_OUT"
pass "API_TOKEN 未提及 → rc=0 (entrypoint 自動產生)"

# 14. PUBLIC_BASE_URL=https + REDIS_PASSWORD 未設定 → rc=1（production 阻斷）
body="${BASE_ENV}PUBLIC_BASE_URL=https://ccas.example.com
"
if run_check "$body"; then
  fail "https + 空 REDIS_PASSWORD 應 rc=1; out=$LAST_OUT"
fi
printf '%s' "$LAST_OUT" | grep -q "HTTPS production 部署必須設定 REDIS_PASSWORD" \
  || fail "https + 空 REDIS_PASSWORD 訊息缺對應字樣; out=$LAST_OUT"
pass "PUBLIC_BASE_URL=https + 空 REDIS_PASSWORD → rc=1（阻斷）"

# 15. PUBLIC_BASE_URL=https + REDIS_PASSWORD 已設定 → rc=0
body="${BASE_ENV}PUBLIC_BASE_URL=https://ccas.example.com
REDIS_PASSWORD=strong-secret
"
run_check "$body" || fail "https + 有值 REDIS_PASSWORD 應 rc=0; out=$LAST_OUT"
pass "PUBLIC_BASE_URL=https + 有值 REDIS_PASSWORD → rc=0"

# 16. PUBLIC_BASE_URL=http（dev）+ REDIS_PASSWORD 未設定 → rc=0（僅 WARN 不阻斷）
body="${BASE_ENV}PUBLIC_BASE_URL=http://localhost:8080
"
run_check "$body" || fail "http + 空 REDIS_PASSWORD 應 rc=0（dev 僅 WARN）; out=$LAST_OUT"
printf '%s' "$LAST_OUT" | grep -q "REDIS_PASSWORD 未設定（dev 可接受）" \
  || fail "http + 空 REDIS_PASSWORD 應保留 WARN 字樣; out=$LAST_OUT"
pass "PUBLIC_BASE_URL=http + 空 REDIS_PASSWORD → rc=0（WARN 不阻斷）"

# 17. PUBLIC_BASE_URL 未設定 + REDIS_PASSWORD 未設定 → rc=0（dev 預設 WARN）
run_check "$BASE_ENV" || fail "未設 PUBLIC_BASE_URL + 空 REDIS_PASSWORD 應 rc=0; out=$LAST_OUT"
printf '%s' "$LAST_OUT" | grep -q "REDIS_PASSWORD 未設定（dev 可接受）" \
  || fail "未設 PUBLIC_BASE_URL 應保留 WARN 字樣; out=$LAST_OUT"
pass "未設 PUBLIC_BASE_URL + 空 REDIS_PASSWORD → rc=0（WARN）"

# 18. PUBLIC_BASE_URL=HTTPS（大寫）+ REDIS_PASSWORD 未設定 → rc=1（大小寫不敏感）
body="${BASE_ENV}PUBLIC_BASE_URL=HTTPS://ccas.example.com
"
if run_check "$body"; then
  fail "HTTPS（大寫）+ 空 REDIS_PASSWORD 應 rc=1; out=$LAST_OUT"
fi
printf '%s' "$LAST_OUT" | grep -q "HTTPS production 部署必須設定 REDIS_PASSWORD" \
  || fail "大寫 HTTPS 阻斷訊息缺對應字樣; out=$LAST_OUT"
pass "PUBLIC_BASE_URL=HTTPS（大寫）+ 空 REDIS_PASSWORD → rc=1（大小寫不敏感）"

printf "\n${GREEN}All check-env tests passed.${NC}\n"
