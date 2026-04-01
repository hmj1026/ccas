#!/bin/bash
# CCAS Python Lint & Security Checks
# Shared hook for PostToolUse (Edit + Write)
# Runs: ruff check, pyright, print detection, format check, security scan, secret scan
set -o pipefail

FILE="$1"

# Only process Python files
[[ "$FILE" == *.py ]] || exit 0

# Run uv commands from backend/ where pyproject.toml lives
BACKEND_DIR=$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2>/dev/null)/backend

# 1. Ruff lint
echo "[ruff-check]"
(cd "$BACKEND_DIR" && uv run ruff check "$FILE" 2>&1 | head -20) || true

# 2. Pyright type check
echo "[pyright]"
(cd "$BACKEND_DIR" && uv run pyright "$FILE" 2>&1 | tail -5) || true

# 3. Print detection (skip test files)
if [[ "$FILE" != *test* ]]; then
    PRINTS=$(grep -n "print(" "$FILE" 2>/dev/null | head -5)
    if [[ -n "$PRINTS" ]]; then
        echo "[print-check]"
        echo "$PRINTS"
        echo "[Hook] WARNING: print() found -- use logging instead"
    fi
fi

# 4. Format check + suggestion
FORMAT_OUT=$((cd "$BACKEND_DIR" && uv run ruff format --check "$FILE") 2>&1)
if echo "$FORMAT_OUT" | grep -q "would reformat"; then
    echo "[format-check]"
    echo "[Hook] SUGGESTION: Run uv run ruff format $FILE"
fi

# 5. Security scan (skip test files)
# Detects unsafe operations: eval, exec, unsafe deserialization, shell injection, dynamic import
if [[ "$FILE" != *test* ]]; then
    SECURITY=$(grep -nE "(eval\(|exec\(|subprocess\.call|os\.system\(|__import__)" "$FILE" 2>/dev/null | head -5)
    if [[ -n "$SECURITY" ]]; then
        echo "[security-scan]"
        echo "$SECURITY"
        echo "[Hook] WARNING: potentially unsafe operation found"
    fi
fi

# 6. Hardcoded secret scan
SECRETS=$(grep -nEi "(password|token|api_key|secret|credentials)\s*=\s*[\"'][^\"']*[\"']" "$FILE" 2>/dev/null | head -5)
if [[ -n "$SECRETS" ]]; then
    echo "[secret-scan]"
    echo "$SECRETS"
    echo "[Hook] WARNING: possible hardcoded secret found"
fi
