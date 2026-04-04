#!/bin/bash
# CCAS Alembic Migration Safety Check
# Triggered by PostToolUse (Edit + Write) on migration files
# Checks for: empty downgrade, destructive operations, backward compatibility
set -o pipefail

FILE="$1"

# Only process Alembic migration files
[[ "$FILE" == *alembic/versions/*.py ]] || exit 0

echo "[alembic-migration-check]"

WARN=0

# 1. Check if downgrade() is empty (just pass)
DOWNGRADE_BODY=$(sed -n '/^def downgrade/,/^def \|^$/p' "$FILE" 2>/dev/null | grep -v "^def downgrade" | grep -v "^$")
if echo "$DOWNGRADE_BODY" | grep -qE "^\s*pass\s*$"; then
    echo "[Hook] WARNING: downgrade() is empty (pass only) -- rollback will not work"
    WARN=1
fi

# 2. Check for destructive operations
DESTRUCTIVE=$(grep -niE "(drop_table|drop_column|drop_index|drop_constraint|alter_column)" "$FILE" 2>/dev/null | head -5)
if [[ -n "$DESTRUCTIVE" ]]; then
    echo "[Hook] WARNING: Destructive operation(s) detected:"
    echo "$DESTRUCTIVE"
    echo "[Hook] Ensure backward compatibility and data preservation"
    WARN=1
fi

# 3. Check for raw SQL execution
RAW_SQL=$(grep -niE "(op\.execute|connection\.execute)" "$FILE" 2>/dev/null | head -5)
if [[ -n "$RAW_SQL" ]]; then
    echo "[Hook] INFO: Raw SQL execution detected -- review carefully:"
    echo "$RAW_SQL"
fi

# 4. Reminder
echo "[Hook] REMINDER: Run 'uv run alembic upgrade head' to apply migration"
if [ $WARN -gt 0 ]; then
    echo "[Hook] REMINDER: Test downgrade path with 'uv run alembic downgrade -1'"
fi

exit 0
