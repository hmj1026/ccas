#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RUN_BACKEND="${RUN_BACKEND:-1}"
RUN_FRONTEND="${RUN_FRONTEND:-1}"
VERIFY_CLAUDE_PLUGINS="${VERIFY_CLAUDE_PLUGINS:-1}"

if [ "$VERIFY_CLAUDE_PLUGINS" = "1" ]; then
    echo "=== Claude Plugin Pin Check ==="
    "$REPO_ROOT/scripts/verify-claude-plugins.sh"
fi

echo "=== SSOT Sync Checks ==="
"$REPO_ROOT/scripts/check-env-sync.sh"
"$REPO_ROOT/scripts/sync-docker-image-assets.sh" --check

if [ "$RUN_BACKEND" = "1" ]; then
    echo "=== Backend Checks ==="
    cd "$REPO_ROOT/backend"
    if [ ! -d ".venv" ]; then
        echo "ERROR: backend/.venv not found. Run 'cd backend && uv sync' first." >&2
        exit 1
    fi
    echo "-> ruff check"
    uv run ruff check .
    echo "-> ruff format"
    uv run ruff format --check .
    echo "-> pyright"
    uv run pyright
    echo "-> pytest"
    uv run pytest tests/unit/ --cov --cov-fail-under=70 -q
fi

if [ "$RUN_FRONTEND" = "1" ]; then
    echo "=== Frontend Checks ==="
    cd "$REPO_ROOT/frontend"
    if [ ! -d "node_modules" ]; then
        echo "ERROR: frontend/node_modules not found. Run 'cd frontend && pnpm install' first." >&2
        exit 1
    fi
    echo "-> eslint"
    pnpm run lint
    echo "-> build (tsc + vite)"
    pnpm run build
    echo "-> vitest"
    pnpm run test
fi

echo "=== All checks passed ==="
