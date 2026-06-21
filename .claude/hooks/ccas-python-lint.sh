#!/bin/bash
# CCAS Python Lint & Security Checks
# Shared hook for PostToolUse (Edit + Write)
# Runs: pyright, print detection, security scan, secret scan.
# NOTE: ruff check + ruff format are now handled by the dhpk `python` module
# (post-edit ruff batched at Stop + pre-commit ruff/format/type-check gate) once
# modules=python is enabled in .claude/settings.local.json — removed here to
# avoid double-linting. This hook keeps the ccas-specific pyright-on-edit feedback
# plus the print / unsafe-op / secret greps that the dhpk module does not provide.
set -o pipefail

# PostToolUse hook input: Claude Code delivers tool context as JSON on stdin;
# argv is empty. Resolve file_path from stdin, keep argv as manual-invocation fallback.
FILE="${1:-}"
if [ -z "$FILE" ] && [ ! -t 0 ] && command -v jq >/dev/null 2>&1; then
    FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
fi
[ -n "$FILE" ] || exit 0

# Only process Python files
[[ "$FILE" == *.py ]] || exit 0

# Run uv commands from backend/ where pyproject.toml lives
BACKEND_DIR=$(git -C "$(dirname "$FILE")" rev-parse --show-toplevel 2>/dev/null)/backend
[ -d "$BACKEND_DIR" ] || exit 0

# 1. Pyright type check
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

# 4. Security scan (skip test files)
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
