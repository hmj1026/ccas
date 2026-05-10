#!/bin/bash
# CCAS Session Retrospective Hook (Stop)
# Writes a session summary to the per-project sessions/ directory and emits
# a one-line stderr pointer so the user can find the file.
set -o pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
ENCODED_PATH=$(echo "$PROJECT_ROOT" | tr '/' '-')
SESSIONS_DIR="$HOME/.claude/projects/$ENCODED_PATH/sessions"
mkdir -p "$SESSIONS_DIR"

STAMP=$(date +%Y-%m-%d-%H%M)
OUT="$SESSIONS_DIR/$STAMP.md"

# Counters
CHANGED_PY=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c '\.py$' || true)
CHANGED_TEST=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'test_.*\.py$' || true)
CHANGED_SQL=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -cE '(models|alembic)' || true)
CHANGED_AUTH=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -cE '(auth|token|security|verify)' || true)
NEW_MIGRATIONS=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'alembic/versions/' || true)
STAGED=$(git -C "$PROJECT_ROOT" diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
UNSTAGED=$(git -C "$PROJECT_ROOT" diff --name-only 2>/dev/null | wc -l | tr -d ' ')
UNTRACKED=$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "?")

{
    echo "# Session Retrospective — $STAMP"
    echo
    echo "- **Branch:** \`$BRANCH\`"
    echo "- **Changed files:** py=$CHANGED_PY (tests=$CHANGED_TEST), sql/migrations=$CHANGED_SQL, auth=$CHANGED_AUTH"
    echo "- **Git state:** staged=$STAGED, unstaged=$UNSTAGED, untracked=$UNTRACKED"
    echo
    echo "## Suggested follow-ups"
    [ "$CHANGED_PY" -gt 0 ] && echo "- /python-review (Python edits)"
    [ "$CHANGED_PY" -gt 0 ] && [ "$CHANGED_TEST" -eq 0 ] && echo "- /tdd (Python edits without test updates)"
    [ "$CHANGED_SQL" -gt 0 ] && echo "- database-reviewer (models/alembic edits)"
    [ "$CHANGED_AUTH" -gt 0 ] && echo "- security-reviewer (auth/security touched)"
    [ "$NEW_MIGRATIONS" -gt 0 ] && echo "- Apply: \`uv run alembic upgrade head\` ($NEW_MIGRATIONS new migration file(s))"
    [ "$STAGED" -gt 0 ] && echo "- $STAGED staged file(s) ready to commit"
    [ "$CHANGED_PY" -eq 0 ] && [ "$CHANGED_SQL" -eq 0 ] && [ "$CHANGED_AUTH" -eq 0 ] && echo "- No code changes detected; hooks were sufficient"
    echo
    echo "## Recent commits (this branch, last 5)"
    git -C "$PROJECT_ROOT" log --oneline -5 2>/dev/null || echo "  (no log)"
} > "$OUT"

# Trim sessions older than 30 days to keep dir bounded (best-effort)
find "$SESSIONS_DIR" -name '*.md' -type f -mtime +30 -delete 2>/dev/null || true

echo "[retrospective] Saved → $OUT" >&2
