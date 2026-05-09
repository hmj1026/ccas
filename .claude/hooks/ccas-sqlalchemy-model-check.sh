#!/bin/bash
# CCAS SQLAlchemy Model Validation Hook
# Triggered by PostToolUse (Edit + Write) on models.py files
# Checks for required SQLAlchemy model structure and reminds about migrations

FILE="${1:-}"
if [ -z "$FILE" ] && [ ! -t 0 ] && command -v jq >/dev/null 2>&1; then
    FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
fi
[ -n "$FILE" ] || exit 0

# Only process model files
[[ "$FILE" == *models*.py ]] || exit 0

echo "[sqlalchemy-model-check]"

WARN=0

if ! grep -q "__tablename__" "$FILE"; then
    echo "[Hook] WARNING: __tablename__ not found in $FILE"
    WARN=1
fi

if ! grep -q "Base" "$FILE"; then
    echo "[Hook] WARNING: does not appear to inherit from Base in $FILE"
    WARN=1
fi

echo "[Hook] REMINDER: Run uv run alembic revision --autogenerate -m \"description\" after model changes"

exit 0
