#!/bin/bash
# CCAS Docker Convention Check Hook
# Triggered by PostToolUse (Edit/Write) on Dockerfile and docker-compose files

set -euo pipefail

FILE="${1:-}"
if [ -z "$FILE" ] && [ ! -t 0 ]; then
    PAYLOAD=$(cat)
    if command -v jq >/dev/null 2>&1; then
        FILE=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
    elif command -v python3 >/dev/null 2>&1; then
        FILE=$(printf '%s' "$PAYLOAD" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("tool_input",{}).get("file_path") or "")' 2>/dev/null || true)
    fi
fi
[ -n "$FILE" ] || exit 0

BASENAME="$(basename "$FILE")"

# Only process Docker-related files
case "$BASENAME" in
  Dockerfile*|docker-compose*.yaml|docker-compose*.yml) ;;
  *) exit 0 ;;
esac

WARNINGS=""

if [[ "$BASENAME" == Dockerfile* ]]; then
  # Check for HEALTHCHECK directive in production stage
  if ! grep -q 'HEALTHCHECK' "$FILE" 2>/dev/null; then
    WARNINGS+="⚠️  Missing HEALTHCHECK directive in Dockerfile\n"
  fi

  # Check for non-root user
  if ! grep -q 'USER.*appuser\|USER.*1001' "$FILE" 2>/dev/null; then
    WARNINGS+="⚠️  Missing non-root USER directive (expected appuser/1001)\n"
  fi

  # Check for hardcoded secrets
  if grep -qiE '(password|token|secret|api_key)\s*=' "$FILE" 2>/dev/null; then
    WARNINGS+="🚨 Possible hardcoded secret detected in Dockerfile\n"
  fi

  # Check for OCI labels in production stage
  if ! grep -q 'org.opencontainers.image' "$FILE" 2>/dev/null; then
    WARNINGS+="⚠️  Missing OCI labels (org.opencontainers.image.*)\n"
  fi
fi

if [[ "$BASENAME" == docker-compose* ]]; then
  # Check for 0.0.0.0 port bindings
  if grep -qE 'ports:' "$FILE" 2>/dev/null && grep -qE '"0\.0\.0\.0:' "$FILE" 2>/dev/null; then
    WARNINGS+="⚠️  Port binding to 0.0.0.0 detected — use 127.0.0.1 for local dev\n"
  fi

  # Check for hardcoded secrets in compose
  if grep -qiE '(password|token|secret|api_key):\s*["\x27]?[a-zA-Z0-9]' "$FILE" 2>/dev/null; then
    WARNINGS+="🚨 Possible hardcoded secret in docker-compose — use env_file or .env\n"
  fi
fi

if [[ -n "$WARNINGS" ]]; then
  echo "[docker-check] Conventions check for $BASENAME:"
  echo -e "$WARNINGS"
fi

exit 0
