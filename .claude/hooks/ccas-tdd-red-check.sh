#!/bin/bash
# CCAS TDD RED State Check Hook
# Triggered by PostToolUse (Write) on new test files
# Runs the test to confirm it fails (RED state) before implementation
set -euo pipefail

FILE="${1:-}"
if [ -z "$FILE" ] && [ ! -t 0 ] && command -v jq >/dev/null 2>&1; then
    FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
fi
[ -n "$FILE" ] || exit 0

# Only process new test files (basename match to handle absolute paths)
[[ "$(basename "$FILE")" == test_*.py ]] || exit 0

# Derive project root and run pytest from backend/
PROJECT_ROOT=$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2>/dev/null || true)
[ -n "$PROJECT_ROOT" ] && [ -d "$PROJECT_ROOT/backend" ] || exit 0
cd "$PROJECT_ROOT/backend"

echo "[tdd-red-check] Running $FILE to confirm RED state..."
uv run pytest "$FILE" -x --tb=short 2>&1 | tail -30 || true

exit 0
