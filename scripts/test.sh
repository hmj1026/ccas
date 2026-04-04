#!/usr/bin/env bash
# [Docker/QA] Run tests inside the backend container (tesseract available).
# Requires: docker compose up (containers must be running)
# For local development, use: ./scripts/dev-test.sh
# Usage: ./scripts/test.sh [pytest args...]
# Example: ./scripts/test.sh tests/unit/ -v
set -euo pipefail
exec docker compose exec backend uv run pytest "$@"
