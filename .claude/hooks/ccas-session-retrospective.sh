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

# Check MEMORY.md
if [ -f ~/.claude/projects/-home-paul-projects-ccas/memory/MEMORY.md ]; then
    MEMORY_MOD=$(stat -f %m ~/.claude/projects/-home-paul-projects-ccas/memory/MEMORY.md 2>/dev/null || stat -c %Y ~/.claude/projects/-home-paul-projects-ccas/memory/MEMORY.md 2>/dev/null)
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
echo "════════════════════════════════════════════════════════════════"
