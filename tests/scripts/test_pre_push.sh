#!/usr/bin/env bash
# Exercise the pre-push ref filter in a disposable repository.
# Ref-only pushes (branch deletions, tags on already-pushed commits) skip the
# full check suite; anything that can carry new commits still runs it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$ROOT/scripts/pre-push.sh" "$TMP/hook.sh"
ZERO=0000000000000000000000000000000000000000
SKIP_MSG='pre-push: ref-only push; skipping checks'

cd "$TMP"
git init -q --bare origin.git
git init -q repo
cd repo
git config user.name Test
git config user.email test@example.test
git commit -q --allow-empty -m pushed
git remote add origin "$TMP/origin.git"
git -c core.hooksPath=/dev/null push -q origin HEAD:refs/heads/master
git fetch -q origin
PUSHED="$(git rev-parse HEAD)"
git tag -a v1 -m v1
git commit -q --allow-empty -m local-only
LOCAL="$(git rev-parse HEAD)"
git tag -a v2 -m v2

run_hook() {
    printf '%s\n' "$@" | RUN_BACKEND=0 RUN_FRONTEND=0 bash "$TMP/hook.sh" > "$TMP/output" 2>&1
}

expect_skip() {
    local label="$1"; shift
    if ! run_hook "$@" || ! grep -Fxq "$SKIP_MSG" "$TMP/output"; then
        echo "FAIL: $label must skip checks" >&2; cat "$TMP/output" >&2; exit 1
    fi
}

expect_checks() {
    local label="$1"; shift
    run_hook "$@" || true
    if grep -Fxq "$SKIP_MSG" "$TMP/output"; then
        echo "FAIL: $label must run checks" >&2; exit 1
    fi
}

expect_skip 'branch deletion' "(delete) $ZERO refs/heads/old $PUSHED"
expect_skip 'tag on pushed commit' "refs/tags/v1 $(git rev-parse v1) refs/tags/v1 $ZERO"
expect_skip 'deletion + pushed tag' \
    "(delete) $ZERO refs/heads/old $PUSHED" \
    "refs/tags/v1 $(git rev-parse v1) refs/tags/v1 $ZERO"
expect_checks 'branch push' "refs/heads/master $LOCAL refs/heads/master $PUSHED"
expect_checks 'tag on unpushed commit' "refs/tags/v2 $(git rev-parse v2) refs/tags/v2 $ZERO"
expect_checks 'deletion + branch push' \
    "(delete) $ZERO refs/heads/old $PUSHED" \
    "refs/heads/master $LOCAL refs/heads/master $PUSHED"
expect_checks 'empty ref list' ''
echo 'PASS: ref-only pushes skip checks; pushes carrying commits run them'
