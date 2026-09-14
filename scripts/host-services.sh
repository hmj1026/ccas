#!/usr/bin/env bash
# Install and operate non-Docker CCAS worker/scheduler/API services.
# Redis is intentionally host-managed and is only health-checked here.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
RUNNER="${ROOT_DIR}/scripts/host-service-runner.sh"
SYSTEMD_TEMPLATE_DIR="${ROOT_DIR}/deploy/host-services/systemd"
LAUNCHD_TEMPLATE_DIR="${ROOT_DIR}/deploy/host-services/launchd"
SUPERVISORD_TEMPLATE_DIR="${ROOT_DIR}/deploy/host-services/supervisord"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
LAUNCHD_USER_DIR="${HOME}/Library/LaunchAgents"
SUPERVISORD_STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/supervisord"
SUPERVISORD_CONF="${SUPERVISORD_STATE_DIR}/supervisord.conf"
SUPERVISORD_CONF_DIR="${SUPERVISORD_STATE_DIR}/conf.d"
SUPERVISORD_SOCKET="${SUPERVISORD_STATE_DIR}/supervisord.sock"
SUPERVISORD_PID="${SUPERVISORD_STATE_DIR}/supervisord.pid"
SUPERVISORD_LOG_DIR="${SUPERVISORD_STATE_DIR}/log"
SUPERVISORD_LOG="${SUPERVISORD_LOG_DIR}/supervisord.log"
USER_ID="$(id -u)"

usage() {
  cat <<'EOF'
Usage: ./scripts/host-services.sh [--driver=systemd|launchd|supervisord] \
  <install|uninstall|status|restart|smoke> [worker|scheduler|api|mcp-http|all]

Commands:
  install    Render and enable the selected services.
  uninstall  Stop, disable, and remove the selected service definitions.
  status     Show service-manager status for the selected services.
  restart    Restart the selected services.
  smoke      Check Redis (when needed), service state, RQ, heartbeat, API readiness,
             and MCP HTTP 401 without a Bearer token.

The default target is all. Redis is installed and upgraded by the host package
manager; this script never starts a private Redis process.

Without --driver, Linux prefers a usable systemd user bus and then falls back
to supervisord. macOS uses launchd. CCAS_HOST_SERVICE_DRIVER is the equivalent
environment override with lower priority than --driver.
EOF
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

info() {
  printf '%s\n' "$1"
}

CLI_DRIVER=""
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    --driver=*)
      [[ -z "$CLI_DRIVER" ]] || die "--driver may only be specified once"
      CLI_DRIVER="${arg#--driver=}"
      ;;
    --driver)
      usage >&2
      exit 2
      ;;
    *)
      POSITIONAL+=("$arg")
      ;;
  esac
done

if [[ ${#POSITIONAL[@]} -lt 1 || ${#POSITIONAL[@]} -gt 2 ]]; then
  usage >&2
  exit 2
fi

ACTION="${POSITIONAL[0]}"
TARGET="${POSITIONAL[1]:-all}"

case "$ACTION" in
  install|uninstall|status|restart|smoke) ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

case "$TARGET" in
  worker|scheduler|api|mcp-http|all) ;;
  *)
    die "target must be worker, scheduler, api, mcp-http, or all"
    ;;
esac

HOST_PLATFORM="$(uname -s)"
case "$HOST_PLATFORM" in
  Linux)
    PLATFORM="linux"
    ;;
  Darwin)
    PLATFORM="macos"
    ;;
  *)
    PLATFORM="other"
    ;;
esac

UV_BIN="$(command -v uv || true)"

sed_replacement() {
  printf '%s' "$1" | sed 's/[\\&|]/\\&/g'
}

systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

supervisord_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

require_runtime() {
  if [[ -z "$UV_BIN" ]]; then
    die "uv is not on PATH; run uv sync --frozen from backend/ after installing uv"
  fi
  if [[ ! -x "$RUNNER" ]]; then
    die "service runner is not executable: $RUNNER"
  fi
}

systemd_available() {
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl --user show-environment >/dev/null 2>&1
}

supervisord_available() {
  [[ -n "$UV_BIN" ]] || return 1
  [[ -d "$BACKEND_DIR" ]] || return 1
  "$UV_BIN" run --directory "$BACKEND_DIR" --no-sync python -c \
    'import supervisor' >/dev/null 2>&1
}

systemd_capabilities() {
  printf '%s\n' worker scheduler
}

launchd_capabilities() {
  printf '%s\n' worker scheduler
}

supervisord_capabilities() {
  printf '%s\n' worker scheduler api mcp-http
}

select_driver() {
  local requested="${CLI_DRIVER:-${CCAS_HOST_SERVICE_DRIVER:-}}"

  if [[ -n "$requested" ]]; then
    case "$requested" in
      systemd|launchd|supervisord)
        DRIVER="$requested"
        return
        ;;
      *)
        die "driver must be systemd, launchd, or supervisord"
        ;;
    esac
  fi

  case "$PLATFORM" in
    macos)
      DRIVER="launchd"
      ;;
    linux)
      if systemd_available; then
        DRIVER="systemd"
      elif supervisord_available; then
        DRIVER="supervisord"
      else
        die "no usable host-service driver found; start a systemd user bus or run 'cd backend && uv sync --extra supervisor'"
      fi
      ;;
    other)
      if supervisord_available; then
        DRIVER="supervisord"
      else
        die "unsupported host platform: $HOST_PLATFORM; install supervisord or use Linux systemd/macOS launchd"
      fi
      ;;
  esac
}

assert_driver_contract() {
  local verb
  for verb in install uninstall status restart is_running capabilities; do
    declare -F "${DRIVER}_${verb}" >/dev/null \
      || die "internal error: driver '$DRIVER' missing ${verb}()"
  done
}

SELECTED_SERVICES=()
DRIVER_CAPABILITIES=()

resolve_selected_services() {
  local service found
  DRIVER_CAPABILITIES=()
  while IFS= read -r service; do
    [[ -n "$service" ]] && DRIVER_CAPABILITIES+=("$service")
  done < <("${DRIVER}_capabilities")

  if [[ "$TARGET" == "all" ]]; then
    SELECTED_SERVICES=("${DRIVER_CAPABILITIES[@]}")
    return
  fi

  found=0
  for service in "${DRIVER_CAPABILITIES[@]}"; do
    if [[ "$service" == "$TARGET" ]]; then
      found=1
      break
    fi
  done

  if [[ "$found" == 0 ]]; then
    if [[ "$TARGET" == "api" || "$TARGET" == "mcp-http" ]] && [[ "$DRIVER" != "supervisord" ]]; then
      die "$TARGET is only supported by supervisord; try --driver=supervisord"
    fi
    die "driver '$DRIVER' does not support target '$TARGET'"
  fi
  SELECTED_SERVICES=("$TARGET")
}

selected_services() {
  local service
  for service in "${SELECTED_SERVICES[@]}"; do
    printf '%s\n' "$service"
  done
}

api_selected() {
  local service
  for service in "${SELECTED_SERVICES[@]}"; do
    [[ "$service" == api ]] && return 0
  done
  return 1
}

mcp_http_selected() {
  local service
  for service in "${SELECTED_SERVICES[@]}"; do
    [[ "$service" == mcp-http ]] && return 0
  done
  return 1
}

needs_redis() {
  local service
  for service in "${SELECTED_SERVICES[@]}"; do
    case "$service" in
      worker|scheduler|api) return 0 ;;
    esac
  done
  return 1
}

service_unit_name() {
  printf 'ccas-%s.service' "$1"
}

service_label() {
  printf 'com.ccas.%s' "$1"
}

render_systemd_unit() {
  local service="$1"
  local template="${SYSTEMD_TEMPLATE_DIR}/ccas-${service}.service.in"
  local output="${SYSTEMD_USER_DIR}/$(service_unit_name "$service")"
  local root backend runner uv
  root="$(sed_replacement "$(systemd_quote "$ROOT_DIR")")"
  backend="$(sed_replacement "$(systemd_quote "$BACKEND_DIR")")"
  runner="$(sed_replacement "$(systemd_quote "$RUNNER")")"
  uv="$(sed_replacement "$(systemd_quote "$UV_BIN")")"

  [[ -f "$template" ]] || die "missing systemd template: $template"
  mkdir -p "$SYSTEMD_USER_DIR"
  sed \
    -e "s|__CCAS_ROOT__|${root}|g" \
    -e "s|__CCAS_BACKEND__|${backend}|g" \
    -e "s|__CCAS_RUNNER__|${runner}|g" \
    -e "s|__UV_BIN__|${uv}|g" \
    "$template" > "$output"
  chmod 0644 "$output"
}

render_launchd_agent() {
  local service="$1"
  local template="${LAUNCHD_TEMPLATE_DIR}/com.ccas.${service}.plist.in"
  local output="${LAUNCHD_USER_DIR}/$(service_label "$service").plist"
  local root backend runner uv home label
  root="$(sed_replacement "$ROOT_DIR")"
  backend="$(sed_replacement "$BACKEND_DIR")"
  runner="$(sed_replacement "$RUNNER")"
  uv="$(sed_replacement "$UV_BIN")"
  home="$(sed_replacement "$HOME")"
  label="$(sed_replacement "$(service_label "$service")")"

  [[ -f "$template" ]] || die "missing launchd template: $template"
  mkdir -p "$LAUNCHD_USER_DIR" "$HOME/Library/Logs"
  sed \
    -e "s|__CCAS_ROOT__|${root}|g" \
    -e "s|__CCAS_BACKEND__|${backend}|g" \
    -e "s|__CCAS_RUNNER__|${runner}|g" \
    -e "s|__UV_BIN__|${uv}|g" \
    -e "s|__HOME__|${home}|g" \
    -e "s|__LABEL__|${label}|g" \
    "$template" > "$output"
  chmod 0644 "$output"
}

render_supervisord_config() {
  local template="${SUPERVISORD_TEMPLATE_DIR}/supervisord.conf.in"
  local state confdir socket pid logdir logfile
  state="$(sed_replacement "$SUPERVISORD_STATE_DIR")"
  confdir="$(sed_replacement "$SUPERVISORD_CONF_DIR")"
  socket="$(sed_replacement "$SUPERVISORD_SOCKET")"
  pid="$(sed_replacement "$SUPERVISORD_PID")"
  logdir="$(sed_replacement "$SUPERVISORD_LOG_DIR")"
  logfile="$(sed_replacement "$SUPERVISORD_LOG")"

  [[ -f "$template" ]] || die "missing supervisord template: $template"
  mkdir -p "$SUPERVISORD_STATE_DIR" "$SUPERVISORD_CONF_DIR" "$SUPERVISORD_LOG_DIR"
  sed \
    -e "s|__CCAS_STATE_DIR__|${state}|g" \
    -e "s|__CCAS_CONF_DIR__|${confdir}|g" \
    -e "s|__CCAS_SOCKET__|${socket}|g" \
    -e "s|__CCAS_PIDFILE__|${pid}|g" \
    -e "s|__CCAS_LOGDIR__|${logdir}|g" \
    -e "s|__CCAS_LOGFILE__|${logfile}|g" \
    "$template" > "$SUPERVISORD_CONF"
  chmod 0600 "$SUPERVISORD_CONF"
}

render_supervisord_program() {
  local service="$1"
  local template="${SUPERVISORD_TEMPLATE_DIR}/ccas-${service}.conf.in"
  local output="${SUPERVISORD_CONF_DIR}/ccas-${service}.conf"
  local command runner backend uv logdir
  runner="$(sed_replacement "$(supervisord_quote "$RUNNER")")"
  uv="$(sed_replacement "$(supervisord_quote "$UV_BIN")")"
  backend="$(sed_replacement "$BACKEND_DIR")"
  logdir="$(sed_replacement "$SUPERVISORD_LOG_DIR")"

  [[ -f "$template" ]] || die "missing supervisord program template: $template"
  case "$service" in
    worker|scheduler|api|mcp-http) ;;
    *) die "unsupported supervisord service: $service" ;;
  esac
  command="${runner} ${service} ${uv}"
  sed \
    -e "s|__CCAS_COMMAND__|${command}|g" \
    -e "s|__CCAS_BACKEND__|${backend}|g" \
    -e "s|__CCAS_LOGDIR__|${logdir}|g" \
    "$template" > "$output"
  chmod 0600 "$output"
}

supervisord_ctl() {
  "$UV_BIN" run --directory "$BACKEND_DIR" --no-sync supervisorctl \
    -c "$SUPERVISORD_CONF" "$@"
}

supervisord_daemon_is_running() {
  local pid
  pid="$(supervisord_ctl pid 2>/dev/null)" || return 1
  [[ "$pid" =~ ^[[:space:]]*[0-9]+[[:space:]]*$ ]]
}

supervisord_ensure_daemon() {
  local attempt
  render_supervisord_config
  if supervisord_daemon_is_running; then
    return
  fi

  "$UV_BIN" run --directory "$BACKEND_DIR" --no-sync supervisord \
    -c "$SUPERVISORD_CONF" >/dev/null 2>&1 \
    || die "failed to start supervisord; inspect $SUPERVISORD_LOG"

  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    supervisord_daemon_is_running && return
    sleep 1
  done
  die "supervisord did not become ready; inspect $SUPERVISORD_LOG"
}

supervisord_require_daemon() {
  supervisord_daemon_is_running \
    || die "supervisord is not running; run install first"
}

redis_url() {
  (
    cd "$BACKEND_DIR"
    "$UV_BIN" run --no-sync python -c \
      'from ccas.config import get_settings; print(get_settings().redis_url)'
  )
}

heartbeat_path() {
  (
    cd "$BACKEND_DIR"
    "$UV_BIN" run --no-sync python -c \
      'from pathlib import Path; from ccas.config import get_settings; p=get_settings().scheduler_heartbeat_path; print(p if p.is_absolute() else Path.cwd() / p)'
  )
}

mcp_http_port() {
  (
    cd "$BACKEND_DIR"
    "$UV_BIN" run --no-sync python -c \
      'from ccas.config import get_settings; print(get_settings().mcp_http_port)'
  )
}

check_redis() {
  command -v redis-cli >/dev/null 2>&1 || die "redis-cli is required; install host Redis first"
  local url="$1"
  local reply
  reply="$(redis-cli -u "$url" ping 2>/dev/null || true)"
  [[ "$reply" == "PONG" ]] || die "Redis did not answer PONG; start the host Redis service"
}

preflight() {
  [[ -d "$BACKEND_DIR" ]] || die "backend directory not found: $BACKEND_DIR"
  [[ -f "$ROOT_DIR/.env" ]] || die "create $ROOT_DIR/.env before installing host services"
  if needs_redis; then
    local url
    url="$(redis_url)" || die "cannot load CCAS settings; check API_TOKEN and .env"
    check_redis "$url"
  fi
}

systemd_install() {
  local service="$1"
  render_systemd_unit "$service"
  systemctl --user daemon-reload
  systemctl --user enable --now "$(service_unit_name "$service")"
}

launchd_install() {
  local service="$1"
  local label="$(service_label "$service")"
  local plist="${LAUNCHD_USER_DIR}/${label}.plist"
  render_launchd_agent "$service"
  launchctl bootout "gui/${USER_ID}" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/${USER_ID}" "$plist"
  launchctl enable "gui/${USER_ID}/${label}"
  launchctl kickstart -k "gui/${USER_ID}/${label}"
}

systemd_uninstall() {
  local service="$1"
  local unit="$(service_unit_name "$service")"
  systemctl --user disable --now "$unit" 2>/dev/null || true
  rm -f "${SYSTEMD_USER_DIR}/${unit}"
  systemctl --user daemon-reload
}

systemd_status() {
  systemctl --user --no-pager --full status "$(service_unit_name "$1")"
}

systemd_restart() {
  systemctl --user restart "$(service_unit_name "$1")"
}

systemd_is_running() {
  systemctl --user is-active --quiet "$(service_unit_name "$1")"
}

launchd_uninstall() {
  local service="$1"
  local label="$(service_label "$service")"
  local plist="${LAUNCHD_USER_DIR}/${label}.plist"
  launchctl bootout "gui/${USER_ID}" "$plist" 2>/dev/null || true
  rm -f "$plist"
}

launchd_status() {
  launchctl print "gui/${USER_ID}/$(service_label "$1")"
}

launchd_restart() {
  launchctl kickstart -k "gui/${USER_ID}/$(service_label "$1")"
}

launchd_is_running() {
  launchctl print "gui/${USER_ID}/$(service_label "$1")" >/dev/null
}

supervisord_install() {
  local service="$1"
  supervisord_ensure_daemon
  render_supervisord_program "$service"
  supervisord_ctl reread
  supervisord_ctl update
  supervisord_ctl start "ccas-${service}"
}

supervisord_uninstall() {
  local service="$1"
  local config="${SUPERVISORD_CONF_DIR}/ccas-${service}.conf"
  supervisord_require_daemon
  if [[ -f "$config" ]]; then
    supervisord_ctl stop "ccas-${service}" >/dev/null 2>&1 || true
    rm -f "$config"
    supervisord_ctl reread
    supervisord_ctl update
  fi
}

supervisord_status() {
  local service="$1"
  supervisord_require_daemon
  supervisord_ctl status "ccas-${service}"
}

supervisord_restart() {
  local service="$1"
  supervisord_require_daemon
  supervisord_ctl restart "ccas-${service}"
}

supervisord_is_running() {
  local service="$1"
  local output state
  output="$(supervisord_ctl status "ccas-${service}" 2>/dev/null)" || return 1
  state="$(printf '%s\n' "$output" | awk 'NR == 1 { print $2; exit }')"
  [[ "$state" == RUNNING ]]
}

install_one() {
  "${DRIVER}_install" "$1"
  info "installed and started $1"
}

uninstall_one() {
  "${DRIVER}_uninstall" "$1"
  info "uninstalled $1"
}

status_one() {
  "${DRIVER}_status" "$1"
}

restart_one() {
  "${DRIVER}_restart" "$1"
  info "restarted $1"
}

service_is_running() {
  "${DRIVER}_is_running" "$1"
}

smoke() {
  local url="$1"
  local heartbeat="$2"
  local service
  local code
  local port
  local mcp_url
  if needs_redis; then
    check_redis "$url"
  fi
  for service in "${SELECTED_SERVICES[@]}"; do
    service_is_running "$service" || die "$service is not running"
  done
  if needs_redis; then
    "$UV_BIN" run --directory "$BACKEND_DIR" --no-sync rq info \
      --url "$url" --raw -Q >/dev/null
  fi
  if [[ "$TARGET" == all || "$TARGET" == scheduler ]]; then
    [[ -f "$heartbeat" ]] || die "scheduler heartbeat is missing: $heartbeat"
    find "$heartbeat" -mmin -2 -print -quit | grep -q . \
      || die "scheduler heartbeat is older than two minutes: $heartbeat"
  fi
  if api_selected; then
    command -v curl >/dev/null 2>&1 || die "curl is required for the api readiness check"
    code="$(curl -s -o /dev/null -w '%{http_code}' \
      'http://127.0.0.1:8000/health/ready' 2>/dev/null || printf '000')"
    [[ "$code" == 200 ]] \
      || die "API readiness check failed (http_code=$code) at http://127.0.0.1:8000/health/ready"
  fi
  if mcp_http_selected; then
    command -v curl >/dev/null 2>&1 || die "curl is required for the MCP HTTP auth check"
    port="$(mcp_http_port)" || die "cannot load MCP HTTP port; check API_TOKEN and .env"
    mcp_url="http://127.0.0.1:${port}/mcp"
    code="$(curl -s -o /dev/null -w '%{http_code}' \
      -H 'Accept: application/json, text/event-stream' \
      "$mcp_url" 2>/dev/null || printf '000')"
    [[ "$code" == 401 ]] \
      || die "MCP HTTP auth check failed (http_code=$code) at $mcp_url"
  fi
  info "smoke check passed"
}

select_driver
assert_driver_contract
resolve_selected_services

if [[ "${CCAS_HOST_SERVICES_DRY_RUN:-0}" == 1 ]]; then
  info "driver=${DRIVER}"
  info "targets=${SELECTED_SERVICES[*]}"
  exit 0
fi

require_runtime

case "$ACTION" in
  install)
    preflight
    for service in "${SELECTED_SERVICES[@]}"; do install_one "$service"; done
    ;;
  uninstall)
    for service in "${SELECTED_SERVICES[@]}"; do uninstall_one "$service"; done
    ;;
  status)
    for service in "${SELECTED_SERVICES[@]}"; do status_one "$service"; done
    ;;
  restart)
    for service in "${SELECTED_SERVICES[@]}"; do restart_one "$service"; done
    ;;
  smoke)
    preflight
    smoke "$(redis_url)" "$(heartbeat_path)"
    ;;
esac
