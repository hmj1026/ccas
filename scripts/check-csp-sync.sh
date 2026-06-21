#!/usr/bin/env bash
# Verify the Content-Security-Policy is identical between the two places it is
# defined (defense-in-depth duplication):
#   - frontend/nginx.conf            : `add_header Content-Security-Policy "…"`
#   - backend/src/ccas/api/app.py    : `_CONTENT_SECURITY_POLICY = ( … )`
#
# 用途：CSP 刻意在 nginx（正式流量）與 FastAPI middleware（直連 / 內部除錯）兩處
# 各放一份做 defense in depth。兩處內容必須逐字一致，否則 nginx 與 backend 對
# 同一資源套用不同政策，產生難以察覺的安全/相容落差。此腳本是 check-env-sync.sh
# 的姊妹檢查：靜態抽取兩處 policy 字串，正規化空白後比對。
#
# Usage：
#   ./scripts/check-csp-sync.sh
# Exit 0 if synced, exit 1 if drift detected.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGINX_CONF="${ROOT_DIR}/frontend/nginx.conf"
APP_PY="${ROOT_DIR}/backend/src/ccas/api/app.py"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

for f in "$NGINX_CONF" "$APP_PY"; do
  if [[ ! -f "$f" ]]; then
    printf "${RED}[ERROR]${NC} 找不到 %s\n" "$f" >&2
    exit 1
  fi
done

# 正規化：把連續空白壓成單一空格，去頭尾空白。
normalize() {
  tr '\t' ' ' | tr -s ' ' | sed -E 's/^ +//; s/ +$//'
}

# nginx：抽出每一處 add_header Content-Security-Policy "…" 的引號內容（可能多處）。
extract_nginx_csp() {
  grep -oE 'Content-Security-Policy "[^"]*"' "$NGINX_CONF" \
    | sed -E 's/^Content-Security-Policy "//; s/"$//'
}

# python：抽出 _CONTENT_SECURITY_POLICY = ( … ) 區塊內所有雙引號片段並串接。
extract_python_csp() {
  awk '
    /_CONTENT_SECURITY_POLICY[[:space:]]*=[[:space:]]*\(/ { capture = 1; next }
    capture && /^[[:space:]]*\)/ { capture = 0 }
    capture {
      line = $0
      while (match(line, /"[^"]*"/)) {
        printf "%s", substr(line, RSTART + 1, RLENGTH - 2)
        line = substr(line, RSTART + RLENGTH)
      }
    }
  ' "$APP_PY"
}

drift_errors=()

# 1. nginx 內部多處 add_header 必須彼此一致
nginx_all="$(extract_nginx_csp)"
if [[ -z "$nginx_all" ]]; then
  printf "${RED}[ERROR]${NC} 在 frontend/nginx.conf 找不到 Content-Security-Policy\n" >&2
  exit 1
fi
nginx_csp="$(printf '%s\n' "$nginx_all" | head -1 | normalize)"
while IFS= read -r occ; do
  [[ -z "$occ" ]] && continue
  if [[ "$(printf '%s' "$occ" | normalize)" != "$nginx_csp" ]]; then
    drift_errors+=("frontend/nginx.conf 內多處 CSP 不一致（請統一所有 add_header）")
    break
  fi
done <<< "$nginx_all"

# 2. python 與 nginx 必須一致
python_csp="$(extract_python_csp | normalize)"
if [[ -z "$python_csp" ]]; then
  printf "${RED}[ERROR]${NC} 在 %s 找不到 _CONTENT_SECURITY_POLICY\n" "$APP_PY" >&2
  exit 1
fi
if [[ "$python_csp" != "$nginx_csp" ]]; then
  drift_errors+=(
    "CSP 不一致：api/app.py='${python_csp}' vs frontend/nginx.conf='${nginx_csp}'"
  )
fi

if [[ ${#drift_errors[@]} -gt 0 ]]; then
  printf "${RED}[ERROR]${NC} CSP drift detected（修改 CSP 時兩處必須同步）：\n"
  for msg in "${drift_errors[@]}"; do
    printf "  - %s\n" "$msg"
  done
  exit 1
fi

printf "${GREEN}[OK]${NC} CSP 一致：frontend/nginx.conf == backend api/app.py\n"
exit 0
