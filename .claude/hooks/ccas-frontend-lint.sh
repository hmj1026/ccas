#!/bin/bash
# CCAS Frontend Lint Hook
# Shared hook for PostToolUse (Edit + Write) on TypeScript/React files
# Runs: eslint
set -o pipefail

FILE="$1"

# Only process TypeScript/React files
[[ "$FILE" == *.ts ]] || [[ "$FILE" == *.tsx ]] || exit 0

# Skip config files (vite.config.ts, vitest.config.ts, etc.)
BASENAME=$(basename "$FILE")
[[ "$BASENAME" == *.config.ts ]] && exit 0

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
