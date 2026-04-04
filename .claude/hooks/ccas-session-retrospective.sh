#!/bin/bash
# CCAS Session Retrospective Hook
# Displays a summary checklist for session closeout

echo ""
echo "================================================================"
echo "  [CCAS] Session Retrospective Checklist"
echo "================================================================"
echo ""

# Check which agents were used
echo "[CHECK] Agents used in this session:"
echo "  - Did you run python-reviewer (/python-review)? (for Python code changes)"
echo "  - Did you run tdd-guide (/tdd)? (for new features/tests)"
echo "  - Did you run database-reviewer? (for SQL/Alembic changes)"
echo "  - Did you run security-reviewer? (for auth/input validation)"
echo ""

# Check MEMORY.md (dynamically resolve Claude project memory path)
PROJECT_ROOT_MEM=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
ENCODED_PATH=$(echo "$PROJECT_ROOT_MEM" | tr '/' '-')
MEMORY_FILE="$HOME/.claude/projects/$ENCODED_PATH/memory/MEMORY.md"
if [ -f "$MEMORY_FILE" ]; then
    MEMORY_MOD=$(stat -f %m "$MEMORY_FILE" 2>/dev/null || stat -c %Y "$MEMORY_FILE" 2>/dev/null)
    CURRENT_TIME=$(date +%s)
    TIME_DIFF=$((CURRENT_TIME - MEMORY_MOD))

    if [ $TIME_DIFF -lt 3600 ]; then
        echo "[OK] MEMORY.md was updated recently"
    else
        echo "[WARN] MEMORY.md has not been updated recently"
        echo "   -> Did you document any new patterns or lessons learned?"
    fi
else
    echo "[INFO] No MEMORY.md found yet (will be created on first use)"
fi
echo ""

# Check git status
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
echo "[CHECK] Git status:"
STAGED=$(git -C "$PROJECT_ROOT" diff --cached --name-only 2>/dev/null | wc -l)
UNSTAGED=$(git -C "$PROJECT_ROOT" diff --name-only 2>/dev/null | wc -l)
UNTRACKED=$(git -C "$PROJECT_ROOT" ls-files --others --exclude-standard 2>/dev/null | wc -l)

echo "  Staged:   $STAGED file(s)"
echo "  Unstaged: $UNSTAGED file(s)"
echo "  Untracked: $UNTRACKED file(s)"

if [ $STAGED -gt 0 ]; then
    echo ""
    echo "[WARN] You have staged changes. Remember to commit:"
    echo "   git commit -m \"your message\""
fi
echo ""

# Check if Python source changed but no test files changed
PY_CHANGED=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c '\.py$' || true)
TEST_CHANGED=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'test_.*\.py$' || true)
if [ "$PY_CHANGED" -gt 0 ] && [ "$TEST_CHANGED" -eq 0 ]; then
    echo "[WARN] Python source files changed but no test files were modified"
    echo "   -> Consider adding/updating tests for your changes"
    echo ""
fi

# Check if Alembic migrations were added but not applied
NEW_MIGRATIONS=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'alembic/versions/' || true)
if [ "$NEW_MIGRATIONS" -gt 0 ]; then
    echo "[REMIND] New Alembic migration(s) detected"
    echo "   -> Run: uv run alembic upgrade head"
    echo ""
fi

echo "================================================================"
