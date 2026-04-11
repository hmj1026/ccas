#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

ln -sf ../../scripts/pre-commit.sh "$HOOKS_DIR/pre-commit"
echo "pre-commit hook installed"

ln -sf ../../scripts/pre-push.sh "$HOOKS_DIR/pre-push"
echo "pre-push hook installed"

if ! command -v gitleaks >/dev/null 2>&1; then
    echo ""
    echo "[WARN] gitleaks not found in PATH."
    echo "       The pre-commit hook will SKIP secret scanning until installed."
    echo "       Install with: brew install gitleaks"
fi
