#!/usr/bin/env bash
# ccas-pre-push-stop.sh
# Async Stop hook: runs full pre-push checks in background when files were
# modified this session. Writes results to a session log so the next session
# (or `git push` invocation) can surface them. Lock file prevents concurrent
# runs across overlapping sessions.
set -o pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Skip if nothing changed this session
if git -C "$REPO_ROOT" diff --quiet && git -C "$REPO_ROOT" diff --cached --quiet; then
    exit 0
fi

PRE_PUSH="$REPO_ROOT/scripts/pre-push.sh"
if [ ! -x "$PRE_PUSH" ]; then
    echo "[pre-push-stop] WARN: $PRE_PUSH missing or not executable, skipping" >&2
    exit 0
fi

LOCK="/tmp/ccas-pre-push.lock"
LOG="/tmp/ccas-pre-push.log"

# Single-flight: bail out if a run is already in progress
if [ -f "$LOCK" ]; then
    PID=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[pre-push-stop] another run is in progress (pid=$PID); see $LOG" >&2
        exit 0
    fi
fi

# Surface previous result on the way out (cheap, sync)
if [ -f "$LOG" ] && grep -q '^STATUS=' "$LOG"; then
    PREV=$(grep '^STATUS=' "$LOG" | tail -1)
    echo "[pre-push-stop] previous run: $PREV (full log: $LOG)" >&2
fi

# Detach: write our pid, run, replace log atomically
{
    echo $$ > "$LOCK"
    {
        echo "STARTED=$(date -u +%FT%TZ)"
        echo "BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)"
        if VERIFY_CLAUDE_PLUGINS=0 bash "$PRE_PUSH" 2>&1; then
            echo "STATUS=PASS"
        else
            echo "STATUS=FAIL exit=$?"
        fi
        echo "FINISHED=$(date -u +%FT%TZ)"
    } > "$LOG"
    rm -f "$LOCK"
} &
disown

echo "[pre-push-stop] running in background; log: $LOG" >&2
exit 0
