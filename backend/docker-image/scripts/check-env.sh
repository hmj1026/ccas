#!/usr/bin/env bash
# Validate .env against .env.example.
#
# Required vs optional:
#   - KEY= (empty value in .env.example)  -> REQUIRED: missing causes exit 1
#   - KEY=value (has value in .env.example) -> OPTIONAL: missing causes warning
#   - # KEY=value (commented in .env.example) -> 完全 optional：不會檢查
#
# 額外驗證（CCAS-specific）：
#   - CCAS_VERSION 格式：^(release|local|v\d+(\.\d+){0,2})$
#   - CCAS_DATA_LOCATION / CCAS_CONFIG_LOCATION / CCAS_LOG_LOCATION：
#       已設定但為空字串 → 報錯（避免「忘了填」造成路徑落空）
#   - CCAS_PORT：1-65535 整數
#   - API_TOKEN：完全未設定（沒有此 env 變數）→ OK；顯式設為空字串 → 報錯
#
# Usage:
#   ./scripts/check-env.sh                       # default paths
#   ENV_FILE=.env.test ./scripts/check-env.sh    # override .env path

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
EXAMPLE_FILE="${EXAMPLE_FILE:-$ROOT_DIR/.env.example}"

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

missing_required=()
missing_optional=()
format_errors=()
security_warnings=()

if [[ ! -f "$EXAMPLE_FILE" ]]; then
  printf "${RED}[ERROR]${NC} 找不到 %s\n" "$EXAMPLE_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  printf "${RED}[ERROR]${NC} 找不到 %s\n" "$ENV_FILE" >&2
  printf "請先從 .env.example 建立 .env：\n"
  printf "  cp .env.example .env\n"
  exit 1
fi

# Source .env to get variable values
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Helper: detect if a key was *explicitly* set in env file（即使值為空字串）。
# 這個區分對 §3.3 "set 但為空" 與 §3.3.1 API_TOKEN 邏輯很重要。
is_explicitly_set_in_env_file() {
  local key="$1"
  grep -E "^[[:space:]]*${key}=" "$ENV_FILE" >/dev/null 2>&1
}

# Parse .env.example: extract KEY=VALUE lines (skip comments and blanks)
while IFS= read -r line; do
  # Skip comments and blank lines
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

  # Extract key and default value
  key="${line%%=*}"
  default_value="${line#*=}"

  # Check if variable is set and non-empty in process environment
  actual_value="${!key:-}"

  if [[ -z "$actual_value" ]]; then
    if [[ -z "$default_value" ]]; then
      # Required: no default in .env.example, missing in .env
      missing_required+=("$key")
    else
      # Optional: has default in .env.example, missing in .env
      missing_optional+=("$key")
    fi
  fi
done < "$EXAMPLE_FILE"

# -----------------------------------------------------------------------------
# CCAS-specific format validation
# -----------------------------------------------------------------------------

# CCAS_VERSION 格式
if [[ -n "${CCAS_VERSION:-}" ]]; then
  if ! [[ "$CCAS_VERSION" =~ ^(release|local|v[0-9]+(\.[0-9]+){0,2}(-[A-Za-z0-9.]+)?)$ ]]; then
    format_errors+=("CCAS_VERSION='${CCAS_VERSION}' 不符合允許格式：release / local / vX[.Y[.Z]][-suffix]")
  fi
fi

# CCAS_*_LOCATION 顯式空值偵測
for var in CCAS_DATA_LOCATION CCAS_CONFIG_LOCATION CCAS_LOG_LOCATION; do
  if is_explicitly_set_in_env_file "$var"; then
    if [[ -z "${!var:-}" ]]; then
      format_errors+=("$var 已在 .env 設定但為空字串；請填入路徑或註解該行使用預設值")
    fi
  fi
done

# CCAS_PORT 範圍
if [[ -n "${CCAS_PORT:-}" ]]; then
  if ! [[ "$CCAS_PORT" =~ ^[0-9]+$ ]] || [[ "$CCAS_PORT" -lt 1 ]] || [[ "$CCAS_PORT" -gt 65535 ]]; then
    format_errors+=("CCAS_PORT='${CCAS_PORT}' 不是 1-65535 範圍內的整數")
  fi
fi

# API_TOKEN：未設定 OK，顯式設空才報錯
if is_explicitly_set_in_env_file "API_TOKEN"; then
  if [[ -z "${API_TOKEN:-}" ]]; then
    format_errors+=("API_TOKEN 已在 .env 顯式設為空字串；請註解該行讓 entrypoint 自動產生，或填入實際 token")
  fi
fi

# -----------------------------------------------------------------------------
# Security hardening warnings（Stage 6 A1/A2；非阻斷：只 WARN，不影響 exit_code）
# -----------------------------------------------------------------------------

# A1：以 HTTPS 對外（PUBLIC_BASE_URL=https://…）卻未啟用 Secure cookie，
# session cookie 可能在中間人攻擊下被竊。提醒設 API_COOKIE_SECURE=true。
if [[ "${PUBLIC_BASE_URL:-}" =~ ^https:// ]]; then
  if [[ "${API_COOKIE_SECURE:-}" != "true" ]]; then
    security_warnings+=(
      "PUBLIC_BASE_URL 為 https:// 但 API_COOKIE_SECURE 未設為 true；建議設定 API_COOKIE_SECURE=true 讓 session cookie 僅在 TLS 連線送出"
    )
  fi
fi

# A2：REDIS_PASSWORD 留空。dev / 單機（redis 綁 127.0.0.1）可接受；
# production / redis 可被其他主機觸及時建議設定。
if [[ -z "${REDIS_PASSWORD:-}" ]]; then
  security_warnings+=(
    "REDIS_PASSWORD 未設定（dev 可接受）；production 或 redis 可被其他主機觸及時建議設定 --requirepass 密碼並同步寫入 REDIS_URL"
  )
fi

# 將 API_TOKEN 從 missing_required 移除（spec §3.3.1：未設定不視為 required）
# 因為 .env.example 中 API_TOKEN= 行已被改為註解（# API_TOKEN=），不會出現在 missing_required；
# 此處僅作為防呆 fallback：若有人改回 .env.example 的 API_TOKEN= 為非註解，仍允許未設定。
if [[ ${#missing_required[@]} -gt 0 ]]; then
  filtered_required=()
  for var in "${missing_required[@]}"; do
    if [[ "$var" != "API_TOKEN" ]]; then
      filtered_required+=("$var")
    fi
  done
  if [[ ${#filtered_required[@]} -gt 0 ]]; then
    missing_required=("${filtered_required[@]}")
  else
    missing_required=()
  fi
fi

# -----------------------------------------------------------------------------
# Report results
# -----------------------------------------------------------------------------
exit_code=0

if [[ ${#missing_required[@]} -gt 0 ]]; then
  printf "${RED}[ERROR]${NC} 缺少必要環境變數：\n"
  for var in "${missing_required[@]}"; do
    printf "  - %s\n" "$var"
  done
  exit_code=1
fi

if [[ ${#format_errors[@]} -gt 0 ]]; then
  printf "${RED}[ERROR]${NC} 環境變數格式錯誤：\n"
  for msg in "${format_errors[@]}"; do
    printf "  - %s\n" "$msg"
  done
  exit_code=1
fi

if [[ ${#missing_optional[@]} -gt 0 ]]; then
  printf "${YELLOW}[WARN]${NC} 缺少可選環境變數（將使用預設值）：\n"
  for var in "${missing_optional[@]}"; do
    printf "  - %s\n" "$var"
  done
fi

# 安全性警告（非阻斷）：不影響 exit_code，僅提醒 operator。
if [[ ${#security_warnings[@]} -gt 0 ]]; then
  printf "${YELLOW}[WARN]${NC} 安全性建議（不影響驗證結果）：\n"
  for msg in "${security_warnings[@]}"; do
    printf "  - %s\n" "$msg"
  done
fi

if [[ $exit_code -eq 0 && ${#missing_optional[@]} -eq 0 && ${#security_warnings[@]} -eq 0 ]]; then
  printf "${GREEN}[OK]${NC} 環境變數驗證通過\n"
fi

exit $exit_code
