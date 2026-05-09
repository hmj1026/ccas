#!/usr/bin/env bash
# Verify docker/example.env is a strict subset of .env.example with consistent
# default values for shared keys.
#
# 用途：
#   - .env.example 是 SSOT（dev / 完整文件）
#   - docker/example.env 是 prod 對外發布版本，僅含使用者需要的 minimal set
#   - docker/example.env 不可有 .env.example 沒有的 key
#   - 共同 key 中「環境語意相同」的（CCAS_VERSION / CCAS_*_LOCATION / CCAS_PORT /
#     LOG_LEVEL / LOG_FORMAT / API_HOST / API_PORT）預設值 SHALL 一致；
#     路徑類（DATABASE_URL / GMAIL_*_PATH / STAGING_DIR / REDIS_URL）與 CORS
#     白名單（FRONTEND_ORIGINS）因 host-relative vs container-absolute 本就不同，
#     不在一致性檢查範圍。
#
# Usage：
#   ./scripts/check-env-sync.sh
# Exit 0 if synced, exit 1 if drift detected.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEV_EXAMPLE="${ROOT_DIR}/.env.example"
PROD_EXAMPLE="${ROOT_DIR}/docker/example.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [[ ! -f "$DEV_EXAMPLE" ]]; then
  printf "${RED}[ERROR]${NC} 找不到 %s\n" "$DEV_EXAMPLE" >&2
  exit 1
fi

if [[ ! -f "$PROD_EXAMPLE" ]]; then
  printf "${RED}[ERROR]${NC} 找不到 %s\n" "$PROD_EXAMPLE" >&2
  exit 1
fi

# 取出 KEY=VALUE 行（忽略空行與註解），格式 "KEY\tVALUE"
extract_kv() {
  local file="$1"
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    /=/ {
      line = $0
      sub(/^[[:space:]]+/, "", line)
      eq = index(line, "=")
      key = substr(line, 1, eq - 1)
      val = substr(line, eq + 1)
      sub(/[[:space:]]+#.*$/, "", val)
      printf "%s\t%s\n", key, val
    }
  ' "$file"
}

# 同時抽出 *commented-out* 的 KEY=...（僅取 key），用於子集成員檢查；
# 確保 dev .env.example 中以 `# KEY=...` 列出的「prod-only / opt-in」變數不會被
# subset check 誤判為「prod 多出來的 key」。
extract_keys_including_commented() {
  local file="$1"
  awk '
    /^[[:space:]]*$/ { next }
    {
      line = $0
      sub(/^[[:space:]]+/, "", line)
      sub(/^#[[:space:]]*/, "", line)
      if (line ~ /^[A-Z][A-Z0-9_]*=/) {
        eq = index(line, "=")
        printf "%s\n", substr(line, 1, eq - 1)
      }
    }
  ' "$file"
}

dev_kv="$(extract_kv "$DEV_EXAMPLE")"
prod_kv="$(extract_kv "$PROD_EXAMPLE")"
dev_all_keys="$(extract_keys_including_commented "$DEV_EXAMPLE")"

drift_errors=()

# 1. 驗證 prod 為 dev 子集 — prod 中所有 key 必須出現在 dev（含已註解條目）
while IFS=$'\t' read -r prod_key prod_val; do
  [[ -z "$prod_key" ]] && continue
  if ! grep -Fxq "$prod_key" <<< "$dev_all_keys"; then
    drift_errors+=("docker/example.env 含 .env.example 不存在的 key: ${prod_key}")
  fi
done <<< "$prod_kv"

# 2. 共同 key 的預設值一致性（僅針對「環境語意相同」的子集）
SHARED_KEYS=(
  CCAS_VERSION
  CCAS_DATA_LOCATION
  CCAS_CONFIG_LOCATION
  CCAS_LOG_LOCATION
  CCAS_PORT
  LOG_LEVEL
  LOG_FORMAT
  API_HOST
  API_PORT
)

is_shared_key() {
  local k="$1"
  for sk in "${SHARED_KEYS[@]}"; do
    [[ "$k" == "$sk" ]] && return 0
  done
  return 1
}

while IFS=$'\t' read -r prod_key prod_val; do
  [[ -z "$prod_key" ]] && continue
  if ! is_shared_key "$prod_key"; then
    continue
  fi
  dev_val="$(grep -E "^${prod_key}\s" <<< "$dev_kv" | head -1 | cut -f2-)"
  if [[ "$prod_val" != "$dev_val" ]]; then
    drift_errors+=("key '${prod_key}' 預設值不一致：.env.example='${dev_val}' vs docker/example.env='${prod_val}'")
  fi
done <<< "$prod_kv"

if [[ ${#drift_errors[@]} -gt 0 ]]; then
  printf "${RED}[ERROR]${NC} env file drift detected:\n"
  for msg in "${drift_errors[@]}"; do
    printf "  - %s\n" "$msg"
  done
  exit 1
fi

printf "${GREEN}[OK]${NC} docker/example.env ⊆ .env.example，且共同 key 預設值一致\n"
exit 0
