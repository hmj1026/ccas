#!/usr/bin/env bash
# QA API 端點自動驗證
# Usage: bash .agents/skills/ccas-qa-acceptance/scripts/qa-api-verify.sh [--base-url URL] [--mode smoke|full]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_URL="http://127.0.0.1:8000"
MODE="full"
PASS_COUNT=0
FAIL_COUNT=0
RESULTS=()
SESSION_COOKIE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Load API token from .env
if [[ -f "$ROOT_DIR/.env" ]]; then
  API_TOKEN=$(grep '^API_TOKEN=' "$ROOT_DIR/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
fi
API_TOKEN="${API_TOKEN:-}"

if [[ -z "$API_TOKEN" ]]; then
  printf "${RED}[FAIL]${NC} API_TOKEN not found in .env\n"
  exit 1
fi

pass() {
  printf "${GREEN}[PASS]${NC} %-6s %-40s %s\n" "$1" "$2" "${3:-}"
  PASS_COUNT=$((PASS_COUNT + 1))
  RESULTS+=("PASS|$1|$2")
}

fail() {
  printf "${RED}[FAIL]${NC} %-6s %-40s %s\n" "$1" "$2" "${3:-}"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  RESULTS+=("FAIL|$1|$2|$3")
}

info() { printf "${CYAN}[INFO]${NC} %s\n" "$1"; }

COOKIE_JAR=$(mktemp)
trap "rm -f $COOKIE_JAR" EXIT

# --- Helper: HTTP request with timing ---
do_request() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local extra_args="${4:-}"

  local url="${BASE_URL}${path}"
  local args=(-s -w "\n%{http_code}\n%{time_total}" -b "$COOKIE_JAR" -c "$COOKIE_JAR")

  if [[ "$method" == "POST" || "$method" == "PATCH" ]]; then
    args+=(-X "$method" -H "Content-Type: application/json")
    if [[ -n "$data" ]]; then
      args+=(-d "$data")
    fi
  elif [[ "$method" == "DELETE" ]]; then
    args+=(-X DELETE)
  fi

  if [[ "$extra_args" != "no-auth" ]]; then
    args+=(-H "Authorization: Bearer $API_TOKEN")
  fi

  curl "${args[@]}" "$url" 2>/dev/null
}

# --- Helper: parse response ---
parse_response() {
  local response="$1"
  local body status time_total
  body=$(echo "$response" | sed '$d' | sed '$d')
  status=$(echo "$response" | tail -2 | head -1)
  time_total=$(echo "$response" | tail -1)
  echo "$status|$time_total|$body"
}

assert_status() {
  local method="$1" path="$2" expected="$3"
  local data="${4:-}" auth="${5:-}"

  local response
  response=$(do_request "$method" "$path" "$data" "$auth")
  local parsed
  parsed=$(parse_response "$response")
  local status
  status=$(echo "$parsed" | cut -d'|' -f1)
  local time_total
  time_total=$(echo "$parsed" | cut -d'|' -f2)

  if [[ "$status" == "$expected" ]]; then
    pass "$method" "$path" "${time_total}s"
  else
    fail "$method" "$path" "expected $expected, got $status"
  fi
  echo "$parsed"
}

assert_json_field() {
  local body="$1" field="$2"
  python3 -c "
import json, sys
try:
    data = json.loads('''$body''')
    keys = '$field'.split('.')
    val = data
    for k in keys:
        val = val[k]
    print(val)
except Exception as e:
    print(f'MISSING: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null
}

assert_header() {
  local path="$1" header="$2" expected="$3"
  local headers
  headers=$(curl -sI -H "Authorization: Bearer $API_TOKEN" "${BASE_URL}${path}" 2>/dev/null)
  local value
  value=$(echo "$headers" | grep -i "^${header}:" | cut -d: -f2- | tr -d '\r' | xargs)

  if [[ "${value,,}" == "${expected,,}" ]]; then
    pass "HDR" "$path $header" "$value"
  else
    fail "HDR" "$path $header" "expected '$expected', got '$value'"
  fi
}

info "QA API Verification (mode: $MODE, base: $BASE_URL)"
echo "==================================="
echo ""

# =====================================================
# SMOKE endpoints (always run)
# =====================================================

info "--- Health ---"
assert_status "GET" "/health" "200" > /dev/null

info "--- Auth Flow ---"
# Login
RESPONSE=$(do_request "POST" "/api/auth/session" '{"token":"'"$API_TOKEN"'"}' "no-auth")
PARSED=$(parse_response "$RESPONSE")
STATUS=$(echo "$PARSED" | cut -d'|' -f1)
if [[ "$STATUS" == "204" ]]; then
  pass "POST" "/api/auth/session (login)" ""
else
  fail "POST" "/api/auth/session (login)" "expected 204, got $STATUS"
fi

info "--- Overview ---"
assert_status "GET" "/api/overview" "200" > /dev/null

info "--- Bills ---"
assert_status "GET" "/api/bills" "200" > /dev/null

info "--- Transactions ---"
assert_status "GET" "/api/transactions" "200" > /dev/null

if [[ "$MODE" == "smoke" ]]; then
  echo ""
  echo "==================================="
  printf "Smoke results: ${GREEN}%d PASS${NC} / ${RED}%d FAIL${NC}\n" "$PASS_COUNT" "$FAIL_COUNT"
  [[ $FAIL_COUNT -gt 0 ]] && exit 1
  exit 0
fi

# =====================================================
# FULL mode: all endpoints
# =====================================================
echo ""

info "--- Auth: session check ---"
assert_status "GET" "/api/auth/session" "200" "" "no-auth" > /dev/null

info "--- Auth: logout ---"
assert_status "DELETE" "/api/auth/session" "204" > /dev/null

# Re-login for subsequent tests
do_request "POST" "/api/auth/session" '{"token":"'"$API_TOKEN"'"}' "no-auth" > /dev/null

info "--- Bills: filters ---"
assert_status "GET" "/api/bills?status=unpaid" "200" > /dev/null
assert_status "GET" "/api/bills?page=9999" "200" > /dev/null

# Get a bill ID for detail tests
BILLS_RESPONSE=$(do_request "GET" "/api/bills?page_size=1")
BILLS_PARSED=$(parse_response "$BILLS_RESPONSE")
BILLS_BODY=$(echo "$BILLS_PARSED" | cut -d'|' -f3-)
BILL_ID=$(python3 -c "
import json
try:
    data = json.loads('''$BILLS_BODY''')
    items = data.get('data', [])
    if items:
        print(items[0]['id'])
    else:
        print('')
except:
    print('')
" 2>/dev/null || echo "")

if [[ -n "$BILL_ID" ]]; then
  info "--- Bills: detail (bill_id=$BILL_ID) ---"
  assert_status "GET" "/api/bills/$BILL_ID/transactions" "200" > /dev/null
  assert_status "PATCH" "/api/bills/$BILL_ID" "200" '{"is_paid":true}' > /dev/null
  # Toggle back
  do_request "PATCH" "/api/bills/$BILL_ID" '{"is_paid":false}' > /dev/null
fi

info "--- Transactions: filters ---"
assert_status "GET" "/api/transactions?sort=amount_desc" "200" > /dev/null
assert_status "GET" "/api/transactions?page_size=5" "200" > /dev/null

info "--- Transactions: export ---"
EXPORT_RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $API_TOKEN" \
  -b "$COOKIE_JAR" "${BASE_URL}/api/transactions/export" 2>/dev/null)
EXPORT_STATUS=$(echo "$EXPORT_RESPONSE" | tail -1)
if [[ "$EXPORT_STATUS" == "200" ]]; then
  pass "GET" "/api/transactions/export" "CSV"
else
  fail "GET" "/api/transactions/export" "expected 200, got $EXPORT_STATUS"
fi

info "--- Analytics ---"
assert_status "GET" "/api/analytics/years" "200" > /dev/null
assert_status "GET" "/api/analytics/trend" "200" > /dev/null
assert_status "GET" "/api/analytics/categories" "200" > /dev/null
assert_status "GET" "/api/analytics/banks" "200" > /dev/null

info "--- Settings: banks ---"
assert_status "GET" "/api/settings/banks" "200" > /dev/null

info "--- Settings: categories ---"
assert_status "GET" "/api/settings/categories" "200" > /dev/null

# CRUD test: create → update → delete category
info "--- Settings: categories CRUD ---"
CREATE_RESP=$(do_request "POST" "/api/settings/categories" '{"keyword":"__qa_test__","category":"QA Test"}')
CREATE_PARSED=$(parse_response "$CREATE_RESP")
CREATE_STATUS=$(echo "$CREATE_PARSED" | cut -d'|' -f1)
CREATE_BODY=$(echo "$CREATE_PARSED" | cut -d'|' -f3-)

if [[ "$CREATE_STATUS" == "201" ]]; then
  pass "POST" "/api/settings/categories (create)" ""
  CAT_ID=$(python3 -c "import json; print(json.loads('''$CREATE_BODY''').get('data',{}).get('id',''))" 2>/dev/null || echo "")

  if [[ -n "$CAT_ID" ]]; then
    assert_status "PATCH" "/api/settings/categories/$CAT_ID" "200" '{"keyword":"__qa_test_updated__"}' > /dev/null
    assert_status "DELETE" "/api/settings/categories/$CAT_ID" "204" > /dev/null
  fi
else
  fail "POST" "/api/settings/categories (create)" "expected 201, got $CREATE_STATUS"
fi

info "--- Staged Attachments ---"
assert_status "GET" "/api/staged-attachments" "200" > /dev/null

info "--- Pipeline Trigger ---"
assert_status "POST" "/api/pipeline/trigger" "200" '{}' > /dev/null

info "--- 401 Unauthorized ---"
UNAUTH_RESPONSE=$(curl -s -w "\n%{http_code}" "${BASE_URL}/api/bills" 2>/dev/null)
UNAUTH_STATUS=$(echo "$UNAUTH_RESPONSE" | tail -1)
if [[ "$UNAUTH_STATUS" == "401" ]]; then
  pass "GET" "/api/bills (no auth)" "401"
else
  fail "GET" "/api/bills (no auth)" "expected 401, got $UNAUTH_STATUS"
fi

info "--- Security Headers ---"
assert_header "/api/overview" "X-Content-Type-Options" "nosniff"
assert_header "/api/overview" "X-Frame-Options" "DENY"
assert_header "/api/overview" "Referrer-Policy" "strict-origin-when-cross-origin"

# =====================================================
# Summary
# =====================================================
echo ""
echo "==================================="
printf "API Verification: ${GREEN}%d PASS${NC} / ${RED}%d FAIL${NC} (total: %d)\n" \
  "$PASS_COUNT" "$FAIL_COUNT" "$((PASS_COUNT + FAIL_COUNT))"

# Save results to JSON
RESULTS_FILE="$ROOT_DIR/test-results/qa-api-results-$(date +%Y-%m-%d).json"
python3 -c "
import json
results = []
for r in '''$(printf '%s\n' "${RESULTS[@]}")'''.strip().split('\n'):
    parts = r.split('|')
    results.append({
        'status': parts[0],
        'method': parts[1] if len(parts) > 1 else '',
        'path': parts[2] if len(parts) > 2 else '',
        'detail': parts[3] if len(parts) > 3 else ''
    })
print(json.dumps({'pass': $PASS_COUNT, 'fail': $FAIL_COUNT, 'results': results}, indent=2))
" > "$RESULTS_FILE" 2>/dev/null && info "Results saved: $RESULTS_FILE"

[[ $FAIL_COUNT -gt 0 ]] && exit 1
exit 0
