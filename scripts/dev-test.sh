#!/usr/bin/env bash
# Run pytest locally (developer workflow, no Docker required).
# Tests use in-memory SQLite — no tesseract or Redis needed.
# Usage: ./scripts/dev-test.sh [pytest args...]
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec uv run pytest "$@"
