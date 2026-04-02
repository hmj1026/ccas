#!/usr/bin/env bash
# Validate .env against .env.example.
#
# Required vs optional:
#   - KEY= (empty value in .env.example)  -> REQUIRED: missing causes exit 1
#   - KEY=value (has value in .env.example) -> OPTIONAL: missing causes warning
#
# Usage:
#   ./scripts/check-env.sh              # default paths
#   ENV_FILE=.env.test ./scripts/check-env.sh  # override .env path

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
source "$ENV_FILE"
set +a

# Parse .env.example: extract KEY=VALUE lines (skip comments and blanks)
while IFS= read -r line; do
  # Skip comments and blank lines
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

  # Extract key and default value
  key="${line%%=*}"
  default_value="${line#*=}"

  # Check if variable is set and non-empty in .env
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

# Report results
exit_code=0

if [[ ${#missing_required[@]} -gt 0 ]]; then
  printf "${RED}[ERROR]${NC} 缺少必要環境變數：\n"
  for var in "${missing_required[@]}"; do
    printf "  - %s\n" "$var"
  done
  exit_code=1
fi

if [[ ${#missing_optional[@]} -gt 0 ]]; then
  printf "${YELLOW}[WARN]${NC} 缺少可選環境變數（將使用預設值）：\n"
  for var in "${missing_optional[@]}"; do
    printf "  - %s\n" "$var"
  done
fi

if [[ $exit_code -eq 0 && ${#missing_optional[@]} -eq 0 ]]; then
  printf "${GREEN}[OK]${NC} 環境變數驗證通過\n"
fi

exit $exit_code
