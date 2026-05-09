#!/usr/bin/env bash
# QA 資料庫重置與驗證
# Usage: bash .agents/skills/ccas-qa-acceptance/scripts/qa-db-reset.sh [--verify-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

VERIFY_ONLY=false
ERRORS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=true; shift ;;
    *) shift ;;
  esac
done

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1"; ERRORS=$((ERRORS + 1)); }
info() { printf "${CYAN}[INFO]${NC} %s\n" "$1"; }

cd "$ROOT_DIR"

if [[ "$VERIFY_ONLY" == false ]]; then
  info "Step 1: Alembic downgrade base"
  docker compose exec -T backend uv run alembic downgrade base

  info "Step 2: Alembic upgrade head"
  docker compose exec -T backend uv run alembic upgrade head

  info "Step 3: Seed bank_configs"
  docker compose exec -T backend uv run python -m ccas.tools.bank_configs \
    --config /data/../config/banks.yaml \
    --registry /data/../config/bank-code-registry.yaml \
    --apply 2>&1 || \
  docker compose exec -T backend uv run python -m ccas.tools.bank_configs --apply 2>&1

  info "Step 4: Seed categories"
  docker compose exec -T backend uv run python -m ccas.tools.categories --apply 2>&1
fi

info "Verifying database state..."

VERIFY_SCRIPT='
import asyncio
import json
from ccas.storage.database import get_engine, get_session_factory
from sqlalchemy import text

async def verify():
    result = {}
    sf = get_session_factory()
    async with sf() as s:
        # Table counts
        for table in ["bank_configs", "categories", "bills", "transactions", "staged_attachments"]:
            try:
                count = (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar()
                result[table] = count
            except Exception as e:
                result[table] = f"ERROR: {e}"

        # WAL mode
        try:
            mode = (await s.execute(text("PRAGMA journal_mode"))).scalar()
            result["journal_mode"] = mode
        except Exception as e:
            result["journal_mode"] = f"ERROR: {e}"

    await get_engine().dispose()
    print(json.dumps(result))

asyncio.run(verify())
'

DB_STATE=$(docker compose exec -T backend uv run python -c "$VERIFY_SCRIPT" 2>/dev/null)

if [[ -z "$DB_STATE" ]]; then
  fail "無法取得 DB 狀態"
  exit 1
fi

BANK_CONFIGS=$(echo "$DB_STATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bank_configs', 'N/A'))")
CATEGORIES=$(echo "$DB_STATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('categories', 'N/A'))")
BILLS=$(echo "$DB_STATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bills', 'N/A'))")
TRANSACTIONS=$(echo "$DB_STATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transactions', 'N/A'))")
WAL_MODE=$(echo "$DB_STATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('journal_mode', 'N/A'))")

if [[ "$BANK_CONFIGS" == "7" ]]; then
  pass "bank_configs = 7"
else
  fail "bank_configs = $BANK_CONFIGS (expected 7)"
fi

if [[ "$CATEGORIES" != "0" && "$CATEGORIES" != "N/A" ]]; then
  pass "categories = $CATEGORIES"
else
  fail "categories = $CATEGORIES (expected > 0)"
fi

if [[ "$VERIFY_ONLY" == false ]]; then
  if [[ "$BILLS" == "0" ]]; then
    pass "bills = 0 (clean state)"
  else
    fail "bills = $BILLS (expected 0 after reset)"
  fi

  if [[ "$TRANSACTIONS" == "0" ]]; then
    pass "transactions = 0 (clean state)"
  else
    fail "transactions = $TRANSACTIONS (expected 0 after reset)"
  fi
fi

if [[ "$WAL_MODE" == "wal" ]]; then
  pass "journal_mode = wal"
else
  fail "journal_mode = $WAL_MODE (expected wal)"
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
  printf "${RED}DB verification: %d error(s)${NC}\n" "$ERRORS"
  exit 1
else
  printf "${GREEN}DB verification: PASS${NC}\n"
fi
