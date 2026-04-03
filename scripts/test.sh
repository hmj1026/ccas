#!/usr/bin/env bash
# Run tests inside the backend container (tesseract available).
# Usage: ./scripts/test.sh [pytest args...]
# Example: ./scripts/test.sh tests/unit/ -v
set -euo pipefail
exec docker compose exec backend uv run pytest "$@"
