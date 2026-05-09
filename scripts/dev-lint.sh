#!/usr/bin/env bash
# Run ruff + pyright locally (developer workflow).
# Usage: ./scripts/dev-lint.sh
set -euo pipefail
cd "$(dirname "$0")/../backend"
uv run ruff check .
uv run ruff format --check .
uv run pyright
