#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RUN_BACKEND="${RUN_BACKEND:-1}"
RUN_FRONTEND="${RUN_FRONTEND:-1}"

# Ref-only pushes carry no unchecked commits: branch deletions, and tags whose
# commit is already on a remote-tracking branch (e.g. a release tag on the
# merged master commit). Anything else, including an empty ref list, runs the
# full suite. stdin lines: <local ref> <local sha> <remote ref> <remote sha>.
ref_only_push() {
    local local_ref local_sha remote_ref _remote_sha commit seen=0
    while read -r local_ref local_sha remote_ref _remote_sha; do
        [ -n "$local_ref" ] || continue
        seen=1
        [[ "$local_sha" =~ ^0+$ ]] && continue
        [[ "$remote_ref" == refs/tags/* ]] || return 1
        commit="$(git rev-parse --verify --quiet "$local_sha^{commit}")" || return 1
        [ -n "$(git for-each-ref --contains "$commit" --count=1 refs/remotes)" ] || return 1
    done
    [ "$seen" = 1 ]
}

if ref_only_push; then
    echo "pre-push: ref-only push; skipping checks"
    exit 0
fi

echo "=== Documentation & Workflow Tool Checks ==="
python3 "$REPO_ROOT/scripts/check_docs.py" --root "$REPO_ROOT"
python3 -m unittest discover -s "$REPO_ROOT/tests/scripts" -p 'test_*.py'

echo "=== SSOT Sync Checks ==="
"$REPO_ROOT/scripts/check-env-sync.sh"
"$REPO_ROOT/scripts/check-csp-sync.sh"
"$REPO_ROOT/scripts/sync-docker-image-assets.sh" --check

echo "=== Repo Hygiene Check ==="
# Use the repository ignore rules so this gate follows new runtime/cache rules.
# --cached also catches ignored files added with git add -f.
IGNORED_TRACKED=$(git -C "$REPO_ROOT" ls-files --cached --ignored --exclude-per-directory=.gitignore)
if [ -n "$IGNORED_TRACKED" ]; then
    echo "ERROR: 已追蹤檔案命中忽略規則：" >&2
    echo "$IGNORED_TRACKED" >&2
    echo "修法：git rm --cached <file>；應版控的範本則調整 .gitignore" >&2
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
    uv run pytest tests/unit/ -m "not live_fubon and not captcha_model" --cov --cov-report=term:skip-covered --cov-fail-under=80 -q
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
    echo "-> vitest (coverage)"
    pnpm run test --coverage --coverage.reporter=text-summary
fi

echo "=== All checks passed ==="
