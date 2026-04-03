#!/usr/bin/env bash
# Run pipeline inside the backend container.
# Usage: ./scripts/pipeline.sh [pipeline args...]
# Example: ./scripts/pipeline.sh --from parse --bank CTBC --force
set -euo pipefail
exec docker compose exec backend uv run python -m ccas.pipeline "$@"
