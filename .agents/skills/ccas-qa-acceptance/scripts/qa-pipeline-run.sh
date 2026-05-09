#!/usr/bin/env bash
# QA Pipeline 全銀行執行 + DB Snapshot
# Usage: bash .agents/skills/ccas-qa-acceptance/scripts/qa-pipeline-run.sh [--bank BANK] [--snapshot-dir DIR]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SINGLE_BANK=""
SNAPSHOT_DIR="$ROOT_DIR/test-results"
TO_STAGE="classify"
ERRORS=0
BANK_RESULTS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bank) SINGLE_BANK="$2"; shift 2 ;;
    --snapshot-dir) SNAPSHOT_DIR="$2"; shift 2 ;;
    --to) TO_STAGE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1"; ERRORS=$((ERRORS + 1)); }
info() { printf "${CYAN}[INFO]${NC} %s\n" "$1"; }

mkdir -p "$SNAPSHOT_DIR"
cd "$ROOT_DIR"

# --- Get active banks ---
if [[ -n "$SINGLE_BANK" ]]; then
  BANKS="$SINGLE_BANK"
else
  BANKS=$(python3 -c "
import yaml
with open('$ROOT_DIR/config/banks.yaml') as f:
    data = yaml.safe_load(f)
for b in data.get('banks', []):
    if b.get('is_active', True):
        print(b['bank_code'])
" 2>/dev/null)
fi

if [[ -z "$BANKS" ]]; then
  fail "No active banks found in config/banks.yaml"
  exit 1
fi

BANK_COUNT=$(echo "$BANKS" | wc -l | tr -d ' ')
info "Running pipeline for $BANK_COUNT bank(s): $(echo $BANKS | tr '\n' ' ')"
echo "---"

TOTAL_START=$(date +%s)

# --- Run pipeline per bank ---
for BANK in $BANKS; do
  info "Pipeline: $BANK"
  BANK_START=$(date +%s)

  if docker compose exec -T backend uv run python -m ccas.pipeline \
    --bank "$BANK" --to "$TO_STAGE" --force 2>&1; then
    BANK_END=$(date +%s)
    DURATION=$((BANK_END - BANK_START))
    pass "$BANK completed in ${DURATION}s"
    BANK_RESULTS+=("$BANK:PASS:${DURATION}s")
  else
    BANK_END=$(date +%s)
    DURATION=$((BANK_END - BANK_START))
    fail "$BANK failed after ${DURATION}s"
    BANK_RESULTS+=("$BANK:FAIL:${DURATION}s")
  fi
  echo ""
done

TOTAL_END=$(date +%s)
TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

# --- DB Snapshot ---
info "Capturing DB snapshot..."

SNAPSHOT_SCRIPT='
import asyncio
import json
from ccas.storage.database import get_engine, get_session_factory
from sqlalchemy import text

async def snapshot():
    result = {"banks": {}, "totals": {}}
    sf = get_session_factory()
    async with sf() as s:
        # Per-bank counts
        rows = (await s.execute(text("""
            SELECT b.bank_code,
                   COUNT(DISTINCT bi.id) as bill_count,
                   COUNT(t.id) as txn_count,
                   COALESCE(SUM(bi.total_amount), 0) as total_amount
            FROM bank_configs b
            LEFT JOIN bills bi ON bi.bank_code = b.bank_code
            LEFT JOIN transactions t ON t.bill_id = bi.id
            WHERE b.is_active = 1
            GROUP BY b.bank_code
            ORDER BY b.bank_code
        """))).fetchall()

        for row in rows:
            result["banks"][row[0]] = {
                "bills": row[1],
                "transactions": row[2],
                "total_amount": float(row[3])
            }

        # Totals
        total_bills = (await s.execute(text("SELECT count(*) FROM bills"))).scalar()
        total_txns = (await s.execute(text("SELECT count(*) FROM transactions"))).scalar()
        total_staged = (await s.execute(text("SELECT count(*) FROM staged_attachments"))).scalar()
        result["totals"] = {
            "bills": total_bills,
            "transactions": total_txns,
            "staged_attachments": total_staged
        }

        # Staged status distribution
        status_rows = (await s.execute(text("""
            SELECT status, count(*) FROM staged_attachments GROUP BY status
        """))).fetchall()
        result["staged_status"] = {r[0]: r[1] for r in status_rows}

    await get_engine().dispose()
    print(json.dumps(result, indent=2))

asyncio.run(snapshot())
'

SNAPSHOT_FILE="$SNAPSHOT_DIR/qa-db-snapshot-$(date +%Y-%m-%d).json"
if docker compose exec -T backend uv run python -c "$SNAPSHOT_SCRIPT" > "$SNAPSHOT_FILE" 2>/dev/null; then
  pass "DB snapshot saved: $SNAPSHOT_FILE"
else
  fail "DB snapshot failed"
fi

# --- Summary ---
echo ""
echo "==================================="
info "Pipeline Results (total: ${TOTAL_DURATION}s)"
echo ""
printf "%-10s %-6s %s\n" "Bank" "Status" "Duration"
printf "%-10s %-6s %s\n" "----" "------" "--------"
for entry in "${BANK_RESULTS[@]}"; do
  IFS=':' read -r bank status duration <<< "$entry"
  if [[ "$status" == "PASS" ]]; then
    printf "${GREEN}%-10s %-6s %s${NC}\n" "$bank" "$status" "$duration"
  else
    printf "${RED}%-10s %-6s %s${NC}\n" "$bank" "$status" "$duration"
  fi
done
echo ""

if [[ -f "$SNAPSHOT_FILE" ]]; then
  info "DB Snapshot Summary:"
  python3 -c "
import json
with open('$SNAPSHOT_FILE') as f:
    data = json.load(f)
totals = data.get('totals', {})
print(f\"  Bills: {totals.get('bills', 'N/A')}\")
print(f\"  Transactions: {totals.get('transactions', 'N/A')}\")
print(f\"  Staged Attachments: {totals.get('staged_attachments', 'N/A')}\")
for bank, info in data.get('banks', {}).items():
    print(f\"  {bank}: {info['bills']} bills, {info['transactions']} txns\")
" 2>/dev/null
fi

echo ""
if [[ $ERRORS -gt 0 ]]; then
  printf "${RED}Pipeline: %d error(s)${NC}\n" "$ERRORS"
  exit 1
else
  printf "${GREEN}Pipeline: ALL PASS${NC}\n"
fi
