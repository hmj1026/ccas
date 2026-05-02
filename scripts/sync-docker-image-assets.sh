#!/usr/bin/env bash
# Sync image-baked deploy assets from root SSOT to backend/docker-image/.
#
# 用途：backend image production stage 透過 backend/ build context 複製這些檔案
# 進 image。本腳本確保 backend/docker-image/ 與 root SSOT 一致。
#
# SSOT：
#   - scripts/docker-entrypoint.sh
#   - scripts/check-env.sh
#   - .env.example
#   - config/*.example.yaml
#
# Usage：
#   ./scripts/sync-docker-image-assets.sh             # 同步
#   ./scripts/sync-docker-image-assets.sh --check     # 僅檢查是否漂移（CI 用）

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${ROOT_DIR}/backend/docker-image"

MODE="${1:-sync}"

declare -a FILE_PAIRS=(
  "scripts/docker-entrypoint.sh:scripts/docker-entrypoint.sh"
  "scripts/check-env.sh:scripts/check-env.sh"
  ".env.example:.env.example"
  "config/banks.example.yaml:default-config/banks.example.yaml"
  "config/bank-code-registry.example.yaml:default-config/bank-code-registry.example.yaml"
  "config/categories.example.yaml:default-config/categories.example.yaml"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

drift=0

for pair in "${FILE_PAIRS[@]}"; do
  src="${ROOT_DIR}/${pair%%:*}"
  dst="${TARGET_DIR}/${pair##*:}"

  if [[ ! -f "$src" ]]; then
    printf "${RED}[ERROR]${NC} 來源檔不存在: %s\n" "$src" >&2
    exit 1
  fi

  case "$MODE" in
    --check)
      if [[ ! -f "$dst" ]]; then
        printf "${RED}[DRIFT]${NC} 缺檔: %s\n" "$dst"
        drift=1
        continue
      fi
      if ! cmp -s "$src" "$dst"; then
        printf "${RED}[DRIFT]${NC} 內容不同: %s\n" "$dst"
        drift=1
      fi
      ;;
    sync)
      mkdir -p "$(dirname "$dst")"
      /bin/cp "$src" "$dst"
      if [[ "$src" == *.sh ]]; then
        chmod +x "$dst"
      fi
      printf "  synced: %s -> %s\n" "${pair%%:*}" "${pair##*:}"
      ;;
    *)
      printf "${RED}[ERROR]${NC} 未知 mode: %s（允許 sync 或 --check）\n" "$MODE" >&2
      exit 1
      ;;
  esac
done

if [[ "$MODE" == "--check" ]]; then
  if [[ $drift -ne 0 ]]; then
    printf "${RED}[ERROR]${NC} backend/docker-image/ 與 root SSOT 漂移；請執行 ./scripts/sync-docker-image-assets.sh\n" >&2
    exit 1
  fi
  printf "${GREEN}[OK]${NC} backend/docker-image/ 與 root SSOT 一致\n"
fi
