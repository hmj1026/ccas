#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

STAGED_FILES=$(git diff --cached --name-only --diff-filter=d)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# Secret scan (gitleaks) — runs first so a leak aborts the commit before
# any other check. Uses `gitleaks protect --staged` so only the staged diff
# is scanned (fast path). Config at .gitleaks.toml in repo root.
# ---------------------------------------------------------------------------
if command -v gitleaks >/dev/null 2>&1; then
    echo "-> gitleaks (staged diff)"
    if ! gitleaks protect --staged --redact \
            --config "$REPO_ROOT/.gitleaks.toml" \
            --source "$REPO_ROOT" --no-banner; then
        echo "[ERROR] gitleaks found leaked secrets/PII in staged changes." >&2
        echo "Review above findings. If any is a false positive, add it to" >&2
        echo ".gitleaks.toml allowlist. Bypass only in emergencies via" >&2
        echo "git commit --no-verify." >&2
        exit 1
    fi
else
    echo "[WARN] gitleaks not installed — skipping secret scan." >&2
    echo "       Install: brew install gitleaks" >&2
fi

BACKEND_PY_FILES=()
FRONTEND_TS_FILES=()

while IFS= read -r file; do
    case "$file" in
        backend/*.py)
            BACKEND_PY_FILES+=("$file")
            ;;
        frontend/*.ts|frontend/*.tsx)
            FRONTEND_TS_FILES+=("$file")
            ;;
    esac
done <<< "$STAGED_FILES"

EXIT_CODE=0

if [ ${#BACKEND_PY_FILES[@]} -gt 0 ]; then
    if [ ! -d "$REPO_ROOT/backend/.venv" ]; then
        echo "[WARN] backend/.venv not found, skipping backend checks" >&2
    else
        echo "=== Pre-commit: Backend ==="

        REL_PY_FILES=()
        for f in "${BACKEND_PY_FILES[@]}"; do
            REL_PY_FILES+=("${f#backend/}")
        done

        cd "$REPO_ROOT/backend"

        echo "-> ruff check (staged files)"
        if ! uv run ruff check "${REL_PY_FILES[@]}"; then
            EXIT_CODE=1
        fi

        echo "-> ruff format (staged files)"
        if ! uv run ruff format --check "${REL_PY_FILES[@]}"; then
            EXIT_CODE=1
        fi

        cd "$REPO_ROOT"
    fi
fi

if [ ${#FRONTEND_TS_FILES[@]} -gt 0 ]; then
    if [ ! -d "$REPO_ROOT/frontend/node_modules" ]; then
        echo "[WARN] frontend/node_modules not found, skipping frontend checks" >&2
    else
        echo "=== Pre-commit: Frontend ==="

        REL_TS_FILES=()
        for f in "${FRONTEND_TS_FILES[@]}"; do
            REL_TS_FILES+=("${f#frontend/}")
        done

        cd "$REPO_ROOT/frontend"

        echo "-> eslint (staged files)"
        if ! npx eslint "${REL_TS_FILES[@]}"; then
            EXIT_CODE=1
        fi

        cd "$REPO_ROOT"
    fi
fi

if [ $EXIT_CODE -ne 0 ]; then
    echo "=== Pre-commit checks FAILED ==="
    exit 1
fi

if [ ${#BACKEND_PY_FILES[@]} -gt 0 ] || [ ${#FRONTEND_TS_FILES[@]} -gt 0 ]; then
    echo "=== Pre-commit checks passed ==="
fi
