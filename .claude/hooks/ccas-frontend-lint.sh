#!/bin/bash
# CCAS Frontend Check Hook
# Shared hook for PostToolUse (Edit + Write) on TypeScript/React files
# Runs: eslint, plus a Vitest smoke check when test config changes
set -o pipefail

FILE="${1:-}"
if [ -z "$FILE" ] && [ ! -t 0 ] && command -v jq >/dev/null 2>&1; then
    FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
fi
[ -n "$FILE" ] || exit 0

# Only process TypeScript/React files
[[ "$FILE" == *.ts ]] || [[ "$FILE" == *.tsx ]] || exit 0

BASENAME=$(basename "$FILE")
IS_VITEST_CONFIG=0
case "$BASENAME" in
    vite.config.ts|vitest.config.ts)
        IS_VITEST_CONFIG=1
        ;;
    *.config.ts)
        exit 0
        ;;
esac

# Derive project root and find frontend directory
PROJECT_ROOT=$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2>/dev/null)
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Only run if file is under frontend/
[[ "$FILE" == *frontend/* ]] || exit 0

# Check pnpm is available
command -v pnpm >/dev/null 2>&1 || { echo "[frontend-lint] pnpm not found, skipping"; exit 0; }

# 1. ESLint
echo "[eslint]"
(cd "$FRONTEND_DIR" && pnpm exec eslint "$FILE" 2>&1 | head -20) || true

# 2. Vitest smoke check when test collection config changes
if [ "$IS_VITEST_CONFIG" = "1" ]; then
    echo "[vitest-smoke]"
    echo "[Hook] Verifying pnpm test stays scoped to Vitest unit tests only"
    (cd "$FRONTEND_DIR" && pnpm test 2>&1 | tail -20) || true
fi

# 3. Reminder for Playwright specs
if [[ "$FILE" == *frontend/e2e/*.spec.ts ]]; then
    echo "[playwright-reminder]"
    echo "[Hook] NOTE: frontend/e2e/*.spec.ts are Playwright-only; verify with pnpm e2e, not pnpm test"
fi
