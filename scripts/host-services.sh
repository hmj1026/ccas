#!/usr/bin/env bash
# Install and operate non-Docker CCAS worker/scheduler services.
# Redis is intentionally host-managed and is only health-checked here.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
RUNNER="${ROOT_DIR}/scripts/host-service-runner.sh"
SYSTEMD_TEMPLATE_DIR="${ROOT_DIR}/deploy/host-services/systemd"
LAUNCHD_TEMPLATE_DIR="${ROOT_DIR}/deploy/host-services/launchd"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
LAUNCHD_USER_DIR="${HOME}/Library/LaunchAgents"
USER_ID="$(id -u)"

usage() {
  cat <<'EOF'
Usage: ./scripts/host-services.sh <install|uninstall|status|restart|smoke> [worker|scheduler|all]

Commands:
  install    Render and enable worker/scheduler services for this checkout.
  uninstall  Stop, disable, and remove the rendered services.
  status     Show service-manager status for the selected services.
  restart    Restart the selected services.
  smoke      Check Redis, service state, RQ connectivity, and scheduler heartbeat.

The default target is all. Redis is installed and upgraded by the host package
manager; this script never starts a private Redis process.
EOF
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

info() {
  printf '%s\n' "$1"
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

ACTION="$1"
TARGET="${2:-all}"

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
  worker|scheduler|all) ;;
  *)
    die "target must be worker, scheduler, or all"
    ;;
esac

case "$(uname -s)" in
  Linux)
    PLATFORM="linux"
    ;;
  Darwin)
    PLATFORM="macos"
    ;;
  *)
    die "unsupported host platform: $(uname -s); use Linux systemd or macOS launchd"
    ;;
esac

UV_BIN="$(command -v uv || true)"

if [[ -z "$UV_BIN" ]]; then
  die "uv is not on PATH; run uv sync --frozen from backend/ after installing uv"
fi

if [[ ! -x "$RUNNER" ]]; then
  die "service runner is not executable: $RUNNER"
fi

sed_replacement() {
  printf '%s' "$1" | sed 's/[\\&|]/\\&/g'
}

systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

selected_services() {
  if [[ "$TARGET" == "all" ]]; then
    printf '%s\n' worker scheduler
  else
    printf '%s\n' "$TARGET"
  fi
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
  local url
  url="$(redis_url)" || die "cannot load CCAS settings; check API_TOKEN and .env"
  check_redis "$url"
}

install_linux() {
  local service="$1"
  render_systemd_unit "$service"
  systemctl --user daemon-reload
  systemctl --user enable --now "$(service_unit_name "$service")"
}

install_macos() {
  local service="$1"
  local label="$(service_label "$service")"
  local plist="${LAUNCHD_USER_DIR}/${label}.plist"
  render_launchd_agent "$service"
  launchctl bootout "gui/${USER_ID}" "$plist" 2>/dev/null || true
  launchctl bootstrap "gui/${USER_ID}" "$plist"
  launchctl enable "gui/${USER_ID}/${label}"
  launchctl kickstart -k "gui/${USER_ID}/${label}"
}

install_one() {
  if [[ "$PLATFORM" == "linux" ]]; then
    install_linux "$1"
  else
    install_macos "$1"
  fi
  info "installed and started $1"
}

uninstall_one() {
  local service="$1"
  if [[ "$PLATFORM" == "linux" ]]; then
    local unit="$(service_unit_name "$service")"
    systemctl --user disable --now "$unit" 2>/dev/null || true
    rm -f "${SYSTEMD_USER_DIR}/${unit}"
    systemctl --user daemon-reload
  else
    local label="$(service_label "$service")"
    local plist="${LAUNCHD_USER_DIR}/${label}.plist"
    launchctl bootout "gui/${USER_ID}" "$plist" 2>/dev/null || true
    rm -f "$plist"
  fi
  info "uninstalled $service"
}

status_one() {
  local service="$1"
  if [[ "$PLATFORM" == "linux" ]]; then
    systemctl --user --no-pager --full status "$(service_unit_name "$service")"
  else
    launchctl print "gui/${USER_ID}/$(service_label "$service")"
  fi
}

restart_one() {
  local service="$1"
  if [[ "$PLATFORM" == "linux" ]]; then
    systemctl --user restart "$(service_unit_name "$service")"
  else
    launchctl kickstart -k "gui/${USER_ID}/$(service_label "$service")"
  fi
  info "restarted $service"
}

service_is_running() {
  local service="$1"
  if [[ "$PLATFORM" == "linux" ]]; then
    systemctl --user is-active --quiet "$(service_unit_name "$service")"
  else
    launchctl print "gui/${USER_ID}/$(service_label "$service")" >/dev/null
  fi
}

smoke() {
  local url="$1"
  local heartbeat="$2"
  local service
  check_redis "$url"
  for service in $(selected_services); do
    service_is_running "$service" || die "$service is not running"
  done
  "$UV_BIN" run --directory "$BACKEND_DIR" --no-sync rq info \
    --url "$url" --raw -Q >/dev/null
  if [[ "$TARGET" == "all" || "$TARGET" == "scheduler" ]]; then
    [[ -f "$heartbeat" ]] || die "scheduler heartbeat is missing: $heartbeat"
    find "$heartbeat" -mmin -2 -print -quit | grep -q . \
      || die "scheduler heartbeat is older than two minutes: $heartbeat"
  fi
  info "smoke check passed: Redis, selected services, RQ, and scheduler heartbeat"
}

case "$ACTION" in
  install)
    preflight
    while read -r service; do install_one "$service"; done < <(selected_services)
    ;;
  uninstall)
    while read -r service; do uninstall_one "$service"; done < <(selected_services)
    ;;
  status)
    while read -r service; do status_one "$service"; done < <(selected_services)
    ;;
  restart)
    while read -r service; do restart_one "$service"; done < <(selected_services)
    ;;
  smoke)
    preflight
    smoke "$(redis_url)" "$(heartbeat_path)"
    ;;
esac
