#!/usr/bin/env bash
# ccas-pre-push-stop.sh
# Stop hook: runs full pre-push checks when the session has modified files.
# Skips silently if there are no uncommitted/staged changes.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Skip if nothing changed this session
if git -C "$REPO_ROOT" diff --quiet && git -C "$REPO_ROOT" diff --cached --quiet; then
    exit 0
fi

PRE_PUSH="$REPO_ROOT/scripts/pre-push.sh"
if [ ! -x "$PRE_PUSH" ]; then
    echo "WARNING: $PRE_PUSH not found or not executable, skipping pre-push checks" >&2
    exit 0
fi

echo "=== Session end: running pre-push checks (files were modified) ==="
bash "$PRE_PUSH"
