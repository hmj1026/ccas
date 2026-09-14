#!/usr/bin/env bash
# Contract tests for scripts/host-services.sh.
#
# The suite exercises the public command seam with dry-run selection and fake
# supervisor/uv boundary commands. It never starts a real service manager.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="${ROOT_DIR}/scripts/host-services.sh"
RUNNER="${ROOT_DIR}/scripts/host-service-runner.sh"

TMP_ROOT="$(mktemp -d)"
FAKE_BIN="${TMP_ROOT}/bin"
FAKE_HOME="${TMP_ROOT}/home"
STATE_DIR="${TMP_ROOT}/state"
FAKE_LOG="${TMP_ROOT}/commands.log"
FAKE_DAEMON="${TMP_ROOT}/supervisord.alive"
mkdir -p "$FAKE_BIN" "$FAKE_HOME" "$STATE_DIR"

ENV_BACKUP="${TMP_ROOT}/env.backup"
HAD_ENV=0
if [[ -e "${ROOT_DIR}/.env" ]]; then
  cp "${ROOT_DIR}/.env" "$ENV_BACKUP"
  HAD_ENV=1
fi

cleanup() {
  rm -f "${ROOT_DIR}/.env"
  if [[ "$HAD_ENV" == 1 ]]; then
    cp "$ENV_BACKUP" "${ROOT_DIR}/.env"
  fi
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

cat > "${FAKE_BIN}/uname" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${FAKE_UNAME:-Linux}"
EOF

cat > "${FAKE_BIN}/systemctl" <<'EOF'
#!/usr/bin/env bash
printf 'systemctl %s\n' "$*" >> "${FAKE_LOG:?}"
if [[ "${FAKE_SYSTEMD_AVAILABLE:-0}" == 1 && "$*" == *"show-environment"* ]]; then
  exit 0
fi
exit 1
EOF

cat > "${FAKE_BIN}/redis-cli" <<'EOF'
#!/usr/bin/env bash
printf 'PONG\n'
EOF

cat > "${FAKE_BIN}/curl" <<'EOF'
#!/usr/bin/env bash
printf '%s' "${FAKE_CURL_CODE:-200}"
EOF

cat > "${FAKE_BIN}/uv" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

printf 'uv %s\n' "$*" >> "${FAKE_LOG:?}"

args=("$@")
command_index=-1
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "--no-sync" ]]; then
    command_index=$((i + 1))
    break
  fi
done

command_name="${args[$command_index]:-}"
case "$command_name" in
  python)
    if [[ "$*" == *"import supervisor"* ]]; then
      exit 0
    fi
    if [[ "$*" == *"redis_url"* ]]; then
      printf 'redis://localhost:6379/0\n'
      exit 0
    fi
    if [[ "$*" == *"scheduler_heartbeat_path"* ]]; then
      printf '%s\n' "${FAKE_HEARTBEAT:?}"
      exit 0
    fi
    ;;
  rq)
    exit 0
    ;;
  supervisord)
    : > "${FAKE_DAEMON:?}"
    exit 0
    ;;
  supervisorctl)
    control_args=("${args[@]:$((command_index + 1))}")
    operation=""
    service=""
    skip_next=0
    for arg in "${control_args[@]}"; do
      if [[ "$skip_next" == 1 ]]; then
        skip_next=0
        continue
      fi
      if [[ "$arg" == "-c" ]]; then
        skip_next=1
        continue
      fi
      if [[ -z "$operation" ]]; then
        operation="$arg"
      elif [[ -z "$service" ]]; then
        service="$arg"
      fi
    done
    case "$operation" in
      pid)
        [[ -e "${FAKE_DAEMON:?}" ]] || exit 1
        printf '123\n'
        ;;
      status)
        [[ -e "${FAKE_DAEMON:?}" ]] || exit 1
        printf '%s  %s   pid 123, uptime 0:01:00\n' "$service" "${FAKE_SERVICE_STATE:-RUNNING}"
        ;;
      reread|update|start|stop|restart)
        ;;
      *)
        exit 1
        ;;
    esac
    exit 0
    ;;
  *)
    exit 0
    ;;
esac

exit 0
EOF

chmod +x "${FAKE_BIN}"/*

export FAKE_UNAME=Linux
export FAKE_SYSTEMD_AVAILABLE=0
export FAKE_CURL_CODE=200
export FAKE_HEARTBEAT="${TMP_ROOT}/heartbeat"
export FAKE_LOG FAKE_DAEMON
: > "$FAKE_LOG"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { printf "${GREEN}[PASS]${NC} %s\n" "$1"; }
fail() { printf "${RED}[FAIL]${NC} %s\n" "$1" >&2; exit 1; }

LAST_OUT=""
LAST_RC=0
run_capture() {
  set +e
  LAST_OUT="$(env \
    HOME="$FAKE_HOME" \
    XDG_STATE_HOME="$STATE_DIR" \
    PATH="${FAKE_BIN}:/usr/bin:/bin" \
    "$@" 2>&1)"
  LAST_RC=$?
  set -e
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  printf '%s' "$haystack" | grep -Fq "$needle" \
    || fail "missing '$needle'; output=$haystack"
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"
  if printf '%s' "$haystack" | grep -Fq "$needle"; then
    fail "unexpected '$needle'; output=$haystack"
  fi
}

# Automatic driver selection is observable without uv or a service manager.
FAKE_SYSTEMD_AVAILABLE=1
run_capture env CCAS_HOST_SERVICES_DRY_RUN=1 bash "$SCRIPT" --driver=systemd install
assert_contains "$LAST_OUT" 'driver=systemd'
assert_contains "$LAST_OUT" 'targets=worker scheduler'
pass 'explicit systemd override resolves worker/scheduler'

FAKE_SYSTEMD_AVAILABLE=1
run_capture env CCAS_HOST_SERVICES_DRY_RUN=1 bash "$SCRIPT" install
assert_contains "$LAST_OUT" 'driver=systemd'
pass 'Linux systemd user bus is preferred automatically'

FAKE_SYSTEMD_AVAILABLE=0
run_capture env CCAS_HOST_SERVICES_DRY_RUN=1 bash "$SCRIPT" install
assert_contains "$LAST_OUT" 'driver=supervisord'
assert_contains "$LAST_OUT" 'targets=worker scheduler api'
pass 'Linux falls back to supervisord and exposes api'

FAKE_UNAME=Darwin
run_capture env CCAS_HOST_SERVICES_DRY_RUN=1 bash "$SCRIPT" install
assert_contains "$LAST_OUT" 'driver=launchd'
assert_contains "$LAST_OUT" 'targets=worker scheduler'
pass 'macOS selects launchd automatically'

FAKE_UNAME=Linux
run_capture env CCAS_HOST_SERVICE_DRIVER=launchd CCAS_HOST_SERVICES_DRY_RUN=1 bash "$SCRIPT" status all
assert_contains "$LAST_OUT" 'driver=launchd'
assert_contains "$LAST_OUT" 'targets=worker scheduler'
pass 'environment override is honored'

run_capture env CCAS_HOST_SERVICE_DRIVER=launchd CCAS_HOST_SERVICES_DRY_RUN=1 \
  bash "$SCRIPT" --driver=supervisord status all
assert_contains "$LAST_OUT" 'driver=supervisord'
assert_contains "$LAST_OUT" 'targets=worker scheduler api'
pass 'CLI driver override has higher priority than environment'

: > "$FAKE_LOG"
run_capture bash "$SCRIPT" --driver=systemd status api
[[ "$LAST_RC" -ne 0 ]] || fail 'systemd api mismatch should fail'
assert_contains "$LAST_OUT" 'api is only supported by supervisord'
assert_not_contains "$(cat "$FAKE_LOG")" 'systemctl --user'
pass 'unsupported api target fails before manager commands'

# Prepare the minimum host environment for supervisord lifecycle commands.
printf 'API_TOKEN=test-token\nREDIS_URL=redis://localhost:6379/0\n' > "${ROOT_DIR}/.env"
FAKE_CURL_CODE=200
run_capture bash "$SCRIPT" --driver=supervisord status worker
[[ "$LAST_RC" -ne 0 ]] || fail 'status without a supervisord daemon should fail'
assert_contains "$LAST_OUT" 'supervisord is not running; run install first'
pass 'supervisord status requires an existing daemon'

run_capture bash "$SCRIPT" --driver=supervisord install worker
[[ "$LAST_RC" == 0 ]] || fail "supervisord worker install failed: $LAST_OUT"
WORKER_CONF="${STATE_DIR}/supervisord/conf.d/ccas-worker.conf"
[[ -f "$WORKER_CONF" ]] || fail 'worker supervisord config was not rendered'
assert_contains "$(sed -n '1,160p' "$WORKER_CONF")" 'autorestart=true'
assert_contains "$(sed -n '1,160p' "$WORKER_CONF")" 'command="'
assert_contains "$(cat "$FAKE_LOG")" 'supervisorctl -c'
assert_contains "$(cat "$FAKE_LOG")" 'start ccas-worker'
pass 'supervisord install starts daemon and worker'

run_capture bash "$SCRIPT" --driver=supervisord status worker
[[ "$LAST_RC" == 0 ]] || fail "supervisord status failed: $LAST_OUT"
assert_contains "$LAST_OUT" 'ccas-worker  RUNNING'
pass 'supervisord status reports program state'

run_capture bash "$SCRIPT" --driver=supervisord restart worker
[[ "$LAST_RC" == 0 ]] || fail "supervisord restart failed: $LAST_OUT"
assert_contains "$(cat "$FAKE_LOG")" 'restart ccas-worker'
pass 'supervisord restart targets the selected program'

run_capture bash "$SCRIPT" --driver=supervisord install api
[[ "$LAST_RC" == 0 ]] || fail "supervisord api install failed: $LAST_OUT"
API_CONF="${STATE_DIR}/supervisord/conf.d/ccas-api.conf"
[[ -f "$API_CONF" ]] || fail 'api supervisord config was not rendered'
pass 'supervisord api program is installable'

run_capture bash "$SCRIPT" --driver=supervisord smoke api
[[ "$LAST_RC" == 0 ]] || fail "api smoke check failed: $LAST_OUT"
assert_contains "$LAST_OUT" 'smoke check passed'
pass 'api smoke check accepts HTTP 200 readiness'

FAKE_CURL_CODE=503
run_capture bash "$SCRIPT" --driver=supervisord smoke api
[[ "$LAST_RC" -ne 0 ]] || fail 'api readiness 503 should fail smoke check'
assert_contains "$LAST_OUT" 'API readiness check failed (http_code=503)'
pass 'api smoke check reports degraded readiness'

export FAKE_SERVICE_STATE=STOPPED
FAKE_CURL_CODE=200
run_capture bash "$SCRIPT" --driver=supervisord smoke api
[[ "$LAST_RC" -ne 0 ]] || fail 'stopped api should fail smoke check'
assert_contains "$LAST_OUT" 'api is not running'
pass 'is_running parses non-RUNNING supervisor state'
unset FAKE_SERVICE_STATE

run_capture bash "$SCRIPT" --driver=supervisord uninstall worker
[[ "$LAST_RC" == 0 ]] || fail "supervisord uninstall failed: $LAST_OUT"
[[ ! -f "$WORKER_CONF" ]] || fail 'worker supervisord config was not removed'
assert_contains "$(cat "$FAKE_LOG")" 'stop ccas-worker'
pass 'supervisord uninstall stops and removes one program'

: > "$FAKE_LOG"
run_capture env FAKE_RUNNER_PROBE=1 bash "$RUNNER" api "${FAKE_BIN}/uv"
[[ "$LAST_RC" == 0 ]] || fail "api runner failed: $LAST_OUT"
assert_contains "$(cat "$FAKE_LOG")" \
  'uv run --no-sync uvicorn ccas.api.app:create_app --factory --host 127.0.0.1 --port 8000'
pass 'host-service-runner exposes production API command'

printf "\n${GREEN}All host-services tests passed.${NC}\n"
