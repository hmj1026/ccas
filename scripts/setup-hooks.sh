#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

ln -sf ../../scripts/pre-commit.sh "$HOOKS_DIR/pre-commit"
echo "pre-commit hook installed"

ln -sf ../../scripts/pre-push.sh "$HOOKS_DIR/pre-push"
echo "pre-push hook installed"
