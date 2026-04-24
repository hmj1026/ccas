#!/usr/bin/env bash
# QA 環境與憑證驗證
# Usage: bash .agents/skills/ccas-qa-acceptance/scripts/qa-env-check.sh [--mode smoke|full]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

MODE="full"
ERRORS=0
WARNINGS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; WARNINGS=$((WARNINGS + 1)); }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1"; ERRORS=$((ERRORS + 1)); }
info() { printf "${CYAN}[INFO]${NC} %s\n" "$1"; }

info "QA 環境檢查 (mode: $MODE)"
echo "---"

# --- 1. 既有 .env 驗證 ---
info "1. 驗證 .env"
if [[ -f "$ROOT_DIR/scripts/check-env.sh" ]]; then
  if bash "$ROOT_DIR/scripts/check-env.sh" 2>&1; then
    pass ".env 驗證通過"
  else
    fail ".env 缺少必要變數"
  fi
else
  warn "找不到 scripts/check-env.sh，跳過 .env 驗證"
fi

# --- 2. Docker 版本 ---
info "2. Docker 環境"
if command -v docker &>/dev/null; then
  DOCKER_VERSION=$(docker --version 2>/dev/null | grep -oP '\d+\.\d+' | head -1)
  DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)
  if [[ "$DOCKER_MAJOR" -ge 24 ]]; then
    pass "Docker Engine $DOCKER_VERSION (>= 24)"
  else
    warn "Docker Engine $DOCKER_VERSION (建議 >= 24)"
  fi
else
  fail "Docker 未安裝"
fi

if command -v docker &>/dev/null && docker compose version &>/dev/null; then
  COMPOSE_VERSION=$(docker compose version --short 2>/dev/null)
  pass "Docker Compose $COMPOSE_VERSION"
else
  fail "Docker Compose 未安裝或不可用"
fi

# --- 3. Config YAML ---
info "3. Config 檔案"
for cfg in "config/banks.yaml" "config/categories.yaml" "config/bank-code-registry.yaml"; do
  if [[ -f "$ROOT_DIR/$cfg" ]]; then
    pass "$cfg 存在"
  else
    fail "$cfg 不存在"
  fi
done

if [[ -f "$ROOT_DIR/config/banks.yaml" ]] && command -v python3 &>/dev/null; then
  if python3 -c "import yaml; yaml.safe_load(open('$ROOT_DIR/config/banks.yaml'))" 2>/dev/null; then
    pass "banks.yaml YAML 格式正確"
  else
    fail "banks.yaml YAML 解析失敗"
  fi
fi

# --- 4. Gmail 憑證 ---
if [[ "$MODE" == "full" ]]; then
  info "4. Gmail OAuth 憑證"
  if [[ -f "$ROOT_DIR/.env" ]]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a

    CRED_PATH="${GMAIL_CREDENTIALS_PATH:-}"
    TOKEN_PATH="${GMAIL_TOKEN_PATH:-}"

    if [[ -n "$CRED_PATH" && -f "$ROOT_DIR/$CRED_PATH" ]]; then
      pass "Gmail credentials 存在 ($CRED_PATH)"
    elif [[ -n "$CRED_PATH" ]]; then
      fail "Gmail credentials 不存在: $CRED_PATH"
    else
      warn "GMAIL_CREDENTIALS_PATH 未設定"
    fi

    if [[ -n "$TOKEN_PATH" && -f "$ROOT_DIR/$TOKEN_PATH" ]]; then
      pass "Gmail token 存在 ($TOKEN_PATH)"
    elif [[ -n "$TOKEN_PATH" ]]; then
      warn "Gmail token 不存在: $TOKEN_PATH (可執行 gmail_auth 取得)"
    else
      warn "GMAIL_TOKEN_PATH 未設定"
    fi
  fi

  # --- 5. PDF 密碼 ---
  info "5. 銀行 PDF 密碼"
  if [[ -f "$ROOT_DIR/config/banks.yaml" ]] && command -v python3 &>/dev/null; then
    BANKS=$(python3 -c "
import yaml
with open('$ROOT_DIR/config/banks.yaml') as f:
    data = yaml.safe_load(f)
for b in data.get('banks', []):
    if b.get('is_active', True):
        print(b['bank_code'])
" 2>/dev/null || true)
    for bank in $BANKS; do
      VAR_NAME="PDF_PASSWORD_${bank}"
      if [[ -n "${!VAR_NAME:-}" ]]; then
        pass "$VAR_NAME 已設定"
      else
        warn "$VAR_NAME 未設定 (該銀行 decrypt 會失敗)"
      fi
    done
  fi
fi

# --- 6. Port 可用性 ---
info "6. Port 可用性"
for port in 8000 5173 6379; do
  if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
      warn "Port $port 已被佔用"
    else
      pass "Port $port 可用"
    fi
  elif command -v lsof &>/dev/null; then
    if lsof -i :"$port" &>/dev/null; then
      warn "Port $port 已被佔用"
    else
      pass "Port $port 可用"
    fi
  else
    warn "無法檢查 port $port (ss/lsof 不可用)"
  fi
done

# --- 7. 磁碟空間 ---
info "7. 磁碟空間"
AVAIL_KB=$(df "$ROOT_DIR" | awk 'NR==2{print $4}')
AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
if [[ "$AVAIL_GB" -ge 2 ]]; then
  pass "可用空間 ${AVAIL_GB}GB (>= 2GB)"
else
  warn "可用空間僅 ${AVAIL_GB}GB (建議 >= 2GB)"
fi

# --- Summary ---
echo ""
echo "==================================="
if [[ $ERRORS -gt 0 ]]; then
  printf "${RED}FAIL${NC}: %d error(s), %d warning(s)\n" "$ERRORS" "$WARNINGS"
  exit 1
else
  printf "${GREEN}PASS${NC}: 0 errors, %d warning(s)\n" "$WARNINGS"
  exit 0
fi
