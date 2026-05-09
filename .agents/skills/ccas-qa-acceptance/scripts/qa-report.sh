#!/usr/bin/env bash
# QA 報告產出 + 回歸比對
# Usage: bash .agents/skills/ccas-qa-acceptance/scripts/qa-report.sh [--output DIR] [--mode smoke|full]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

OUTPUT_DIR="$ROOT_DIR/.reports"
MODE="full"
RESULTS_DIR="$ROOT_DIR/test-results"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT_DIR="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

info() { printf "${CYAN}[INFO]${NC} %s\n" "$1"; }
pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }

mkdir -p "$OUTPUT_DIR"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +%Y-%m-%d-%H%M)
REPORT_FILE="$OUTPUT_DIR/qa-acceptance-${TIMESTAMP}.md"
BASELINES_FILE="$OUTPUT_DIR/qa-baselines.json"

info "Generating QA report..."

# --- Collect Docker logs ---
info "Collecting Docker logs..."
docker compose logs --no-color > "$RESULTS_DIR/qa-docker-logs-${TIMESTAMP}.txt" 2>/dev/null || true

# --- Find previous report for regression ---
PREV_REPORT=""
if ls "$OUTPUT_DIR"/qa-acceptance-*.md 1>/dev/null 2>&1; then
  PREV_REPORT=$(ls -t "$OUTPUT_DIR"/qa-acceptance-*.md 2>/dev/null | head -1)
  if [[ "$PREV_REPORT" == "$REPORT_FILE" ]]; then
    PREV_REPORT=$(ls -t "$OUTPUT_DIR"/qa-acceptance-*.md 2>/dev/null | sed -n '2p')
  fi
fi

# --- Read result files ---
API_RESULTS=""
if [[ -f "$RESULTS_DIR/qa-api-results-$(date +%Y-%m-%d).json" ]]; then
  API_RESULTS=$(cat "$RESULTS_DIR/qa-api-results-$(date +%Y-%m-%d).json")
fi

DB_SNAPSHOT=""
if [[ -f "$RESULTS_DIR/qa-db-snapshot-$(date +%Y-%m-%d).json" ]]; then
  DB_SNAPSHOT=$(cat "$RESULTS_DIR/qa-db-snapshot-$(date +%Y-%m-%d).json")
fi

# --- Generate report ---
cat > "$REPORT_FILE" << HEADER
# CCAS QA 驗收報告

- 日期: $(date +%Y-%m-%d)
- 模式: $MODE
- 產出時間: $(date '+%Y-%m-%d %H:%M:%S')

## 摘要

> 此報告由 \`qa-report.sh\` 自動產出。
> 各 Phase 的詳細結果請參考以下各節。

## Phase 結果

HEADER

# Append API results if available
if [[ -n "$API_RESULTS" ]]; then
  API_PASS=$(echo "$API_RESULTS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pass',0))" 2>/dev/null || echo "N/A")
  API_FAIL=$(echo "$API_RESULTS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('fail',0))" 2>/dev/null || echo "N/A")
  cat >> "$REPORT_FILE" << API_SECTION

### Phase 6: API 端點驗證
- PASS: $API_PASS
- FAIL: $API_FAIL
API_SECTION
fi

# Append DB snapshot if available
if [[ -n "$DB_SNAPSHOT" ]]; then
  cat >> "$REPORT_FILE" << DB_SECTION

## DB Snapshot

\`\`\`json
$DB_SNAPSHOT
\`\`\`
DB_SECTION
fi

# --- Regression analysis ---
if [[ -n "$PREV_REPORT" && -f "$PREV_REPORT" ]]; then
  cat >> "$REPORT_FILE" << REGRESSION

## 回歸分析

前次報告: \`$(basename "$PREV_REPORT")\`

REGRESSION

  # Extract FAIL lines from both reports
  PREV_FAILS=$(grep -i "FAIL\|ERROR" "$PREV_REPORT" 2>/dev/null | sort || true)
  CURR_FAILS=$(grep -i "FAIL\|ERROR" "$REPORT_FILE" 2>/dev/null | sort || true)

  NEW_ISSUES=$(comm -13 <(echo "$PREV_FAILS") <(echo "$CURR_FAILS") 2>/dev/null || true)
  RESOLVED=$(comm -23 <(echo "$PREV_FAILS") <(echo "$CURR_FAILS") 2>/dev/null || true)

  if [[ -n "$NEW_ISSUES" ]]; then
    echo "### 新增問題" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "$NEW_ISSUES" | while read -r line; do
      echo "- $line" >> "$REPORT_FILE"
    done
    echo "" >> "$REPORT_FILE"
  fi

  if [[ -n "$RESOLVED" ]]; then
    echo "### 已解決問題" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "$RESOLVED" | while read -r line; do
      echo "- $line" >> "$REPORT_FILE"
    done
    echo "" >> "$REPORT_FILE"
  fi
else
  echo "" >> "$REPORT_FILE"
  echo "## 回歸分析" >> "$REPORT_FILE"
  echo "" >> "$REPORT_FILE"
  echo "首次執行，無前次報告可比對。" >> "$REPORT_FILE"
fi

# --- Footer ---
cat >> "$REPORT_FILE" << FOOTER

---

## 後續行動

- [ ] 修復所有 ERROR 等級問題
- [ ] 調查 VERIFICATION-ISSUE 等級問題
- [ ] 更新效能基準

## Artifacts

| 檔案 | 路徑 |
|------|------|
| 本報告 | \`$REPORT_FILE\` |
| Docker logs | \`$RESULTS_DIR/qa-docker-logs-${TIMESTAMP}.txt\` |
| API results | \`$RESULTS_DIR/qa-api-results-$(date +%Y-%m-%d).json\` |
| DB snapshot | \`$RESULTS_DIR/qa-db-snapshot-$(date +%Y-%m-%d).json\` |
FOOTER

# --- Update baselines ---
info "Updating baselines..."
python3 -c "
import json, os
baselines_path = '$BASELINES_FILE'
existing = {}
if os.path.exists(baselines_path):
    with open(baselines_path) as f:
        existing = json.load(f)

existing['last_run'] = '$(date +%Y-%m-%dT%H:%M:%S)'
existing['mode'] = '$MODE'

# API results
api_path = '$RESULTS_DIR/qa-api-results-$(date +%Y-%m-%d).json'
if os.path.exists(api_path):
    with open(api_path) as f:
        api = json.load(f)
    existing['api_pass'] = api.get('pass', 0)
    existing['api_fail'] = api.get('fail', 0)

# DB snapshot
db_path = '$RESULTS_DIR/qa-db-snapshot-$(date +%Y-%m-%d).json'
if os.path.exists(db_path):
    with open(db_path) as f:
        db = json.load(f)
    existing['db_totals'] = db.get('totals', {})

with open(baselines_path, 'w') as f:
    json.dump(existing, f, indent=2)
" 2>/dev/null && pass "Baselines updated: $BASELINES_FILE"

echo ""
echo "==================================="
pass "Report generated: $REPORT_FILE"
info "Review the report and fill in Phase details manually or via agent."
