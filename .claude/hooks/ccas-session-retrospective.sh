#!/bin/bash
# CCAS Session Retrospective Hook
# Displays a summary checklist for session closeout

echo ""
echo "================================================================"
echo "  [CCAS] Session Retrospective Checklist"
echo "================================================================"
echo ""

# Dynamically suggest agents based on what changed (vs HEAD)
PROJECT_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CHANGED_PY=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c '\.py$' || true)
CHANGED_TEST=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'test_.*\.py$' || true)
CHANGED_SQL=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -cE '(models|alembic)' || true)
CHANGED_AUTH=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -cE '(auth|token|security|verify)' || true)

SUGGESTIONS=0
echo "[AGENTS] 根據本次修改，建議確認執行的後置步驟："
if [ "$CHANGED_PY" -gt 0 ]; then
    echo "  → /python-review  (Python 程式碼有修改)"
    SUGGESTIONS=$((SUGGESTIONS + 1))
fi
if [ "$CHANGED_PY" -gt 0 ] && [ "$CHANGED_TEST" -eq 0 ]; then
    echo "  → /tdd            (Python 修改但無測試更新)"
    SUGGESTIONS=$((SUGGESTIONS + 1))
fi
if [ "$CHANGED_SQL" -gt 0 ]; then
    echo "  → database-reviewer  (models/alembic 有修改)"
    SUGGESTIONS=$((SUGGESTIONS + 1))
fi
if [ "$CHANGED_AUTH" -gt 0 ]; then
    echo "  → security-reviewer  (認證/安全相關有修改)"
    SUGGESTIONS=$((SUGGESTIONS + 1))
fi
if [ "$SUGGESTIONS" -eq 0 ]; then
    echo "  (無 Python/SQL/Auth 修改，hooks 靜態分析已足夠)"
fi
echo ""

# Check MEMORY.md (dynamically resolve Claude project memory path)
ENCODED_PATH=$(echo "$PROJECT_ROOT" | tr '/' '-')
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

# Check if Alembic migrations were added but not applied
NEW_MIGRATIONS=$(git -C "$PROJECT_ROOT" diff --name-only HEAD 2>/dev/null | grep -c 'alembic/versions/' || true)
if [ "$NEW_MIGRATIONS" -gt 0 ]; then
    echo "[REMIND] New Alembic migration(s) detected"
    echo "   -> Run: uv run alembic upgrade head"
    echo ""
fi

echo "================================================================"
