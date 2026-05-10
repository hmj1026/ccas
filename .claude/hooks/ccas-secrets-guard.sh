#!/usr/bin/env bash
# ccas-secrets-guard.sh
# PreToolUse hook: blocks Edit/Write that would commit plaintext secrets to
# config files (.env / yaml / json / toml / config/*). Allows .env.example
# placeholders. Exit 2 -> Claude sees the block reason.
set -o pipefail

# Resolve target file path from PreToolUse stdin JSON; fall back to argv.
FILE="${1:-}"
CONTENT=""
if [ -z "$FILE" ] && [ ! -t 0 ] && command -v jq >/dev/null 2>&1; then
    PAYLOAD=$(cat)
    FILE=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
    # Write tool: full content; Edit tool: new_string; MultiEdit: edits[].new_string
    CONTENT=$(printf '%s' "$PAYLOAD" | jq -r '
        (.tool_input.content // empty),
        (.tool_input.new_string // empty),
        ((.tool_input.edits // []) | map(.new_string // "") | join("\n"))
    ' 2>/dev/null || true)
fi
[ -n "$FILE" ] || exit 0

# Only scan secret-bearing config files
case "$FILE" in
    *.env|*.env.local|*.env.*)
        # Allow example/template files (placeholders expected)
        case "$FILE" in *.example|*.example.*|*.template) exit 0 ;; esac
        ;;
    *.yaml|*.yml|*.json|*.toml) ;;
    */config/*) ;;
    *) exit 0 ;;
esac

# Skip explicit example/template files in any extension
case "$FILE" in *.example*|*.template*) exit 0 ;; esac

# Read content from disk if not present in payload (e.g., MultiEdit on existing file)
if [ -z "$CONTENT" ] && [ -r "$FILE" ]; then
    CONTENT=$(cat "$FILE")
fi
[ -n "$CONTENT" ] || exit 0

# Detection patterns. Each line: <pattern_label>:<egrep regex>
HITS=""
check() {
    local label="$1" regex="$2"
    local match
    match=$(printf '%s' "$CONTENT" | grep -nE "$regex" 2>/dev/null | head -3)
    if [ -n "$match" ]; then
        HITS="${HITS}[${label}]
${match}
"
    fi
}

check "openai-key"      'sk-(proj-)?[A-Za-z0-9_-]{20,}'
check "anthropic-key"   'sk-ant-[A-Za-z0-9_-]{20,}'
check "github-token"    'gh[pousr]_[A-Za-z0-9]{30,}'
check "aws-access-key"  'AKIA[0-9A-Z]{16}'
check "slack-bot-token" 'xox[baprs]-[A-Za-z0-9-]{20,}'
check "bearer-token"    'Bearer[[:space:]]+[A-Za-z0-9._\-]{20,}'
check "private-key"     '-----BEGIN [A-Z ]*PRIVATE KEY-----'
check "credential-assign" '(password|passwd|secret|api[_-]?key|access[_-]?token)[[:space:]]*[:=][[:space:]]*["'\''][^"'\''[:space:]<{${PLACEHOLDER}]{8,}["'\'']'

# Allow common placeholders even in non-example files
PLACEHOLDER='changeme|your[_-]|example|<.*>|xxx+|\.\.\.|\$\{.*\}|TODO'
if [ -n "$HITS" ]; then
    # Strip lines that match placeholder patterns
    FILTERED=$(printf '%s' "$HITS" | grep -vEi "$PLACEHOLDER" || true)
    if [ -n "$FILTERED" ]; then
        echo "[secrets-guard] BLOCKED: $FILE appears to contain plaintext secrets" >&2
        echo "$FILTERED" >&2
        echo "[secrets-guard] Move the value to .env (gitignored) and reference via env vars." >&2
        exit 2
    fi
fi
exit 0
