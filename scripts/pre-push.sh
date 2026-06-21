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
"$REPO_ROOT/scripts/check-csp-sync.sh"
"$REPO_ROOT/scripts/sync-docker-image-assets.sh" --check

echo "=== Repo Hygiene Check ==="
SUSPECT_RE='(^\.claude/scheduled_tasks\.lock$|/\.DS_Store$|/__pycache__/|/\.pytest_cache/|/\.ruff_cache/|/\.mypy_cache/|\.pyc$|^node_modules/|\.pid$|\.sock$|^backend/data/captcha-archive/|^backend/data/staging/|\.bak(\.[^/]*)?$|^\.env$|^\.env\.(local|prod|staging))'
SUSPECT=$(git -C "$REPO_ROOT" ls-files | grep -E "$SUSPECT_RE" || true)
if [ -n "$SUSPECT" ]; then
    echo "ERROR: 偵測到不應追蹤的 runtime / cache / 機敏類型檔：" >&2
    echo "$SUSPECT" >&2
    echo "修法：git rm --cached <file> 並更新 .gitignore" >&2
    exit 1
fi

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
