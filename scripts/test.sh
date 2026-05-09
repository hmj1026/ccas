#!/usr/bin/env bash
# Run pytest locally (production container does not include tests/ or dev deps).
# Usage: ./scripts/test.sh [pytest args...]
# Example: ./scripts/test.sh tests/unit/ -v
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec uv run pytest "$@"
