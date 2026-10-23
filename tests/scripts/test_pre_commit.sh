#!/usr/bin/env bash
# Exercise the hook in a disposable repository with deterministic tool doubles.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/repo/backend/.venv" "$TMP/bin"
cp "$ROOT/scripts/pre-commit.sh" "$TMP/hook.sh"
cat > "$TMP/bin/uv" <<'MOCK'
#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$HOOK_LOG"
if [[ "$*" == 'run ruff format .' ]]; then
    printf 'unexpected rewrite\n' > unrelated.py
fi
if [[ "$*" == 'run pyright' ]]; then exit "${TYPECHECK_EXIT:-0}"; fi
MOCK
printf '#!/usr/bin/env bash\nexit 0\n' > "$TMP/bin/gitleaks"
chmod +x "$TMP/bin/uv" "$TMP/bin/gitleaks"
export PATH="$TMP/bin:$PATH" HOOK_LOG="$TMP/tools.log"
cd "$TMP/repo"
git init -q
git config user.name Test
git config user.email test@example.test
printf 'initial\n' > backend/staged.py
printf 'original\n' > backend/unrelated.py
git add .
git -c core.hooksPath=/dev/null commit -qm initial
printf 'staged change\n' > backend/staged.py
git add backend/staged.py
printf 'unrelated dirty content\n' > backend/unrelated.py
cp backend/unrelated.py "$TMP/expected"
bash "$TMP/hook.sh" > "$TMP/output" 2>&1
cmp backend/unrelated.py "$TMP/expected"
grep -Fx 'run ruff format staged.py' "$HOOK_LOG"
grep -Fx 'run pyright' "$HOOK_LOG"
if TYPECHECK_EXIT=1 bash "$TMP/hook.sh" > "$TMP/output" 2>&1; then
    echo 'FAIL: typecheck failure must block commit' >&2; exit 1
fi
# Auto-fixing/re-staging a partially staged file would include unstaged hunks.
git show :backend/staged.py > "$TMP/index-before"
printf 'unstaged hunk\n' >> backend/staged.py
cp backend/staged.py "$TMP/worktree-before"
: > "$HOOK_LOG"
if bash "$TMP/hook.sh" > "$TMP/output" 2>&1; then
    echo 'FAIL: partially staged Python must block before auto-fix' >&2; exit 1
fi
git show :backend/staged.py > "$TMP/index-after"
cmp "$TMP/index-before" "$TMP/index-after"
cmp "$TMP/worktree-before" backend/staged.py
test ! -s "$HOOK_LOG"
echo 'PASS: staged-only formatting, full typecheck, failure and partial-stage safety'
