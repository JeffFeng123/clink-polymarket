#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
ROOT_REALPATH="$(cd "$ROOT_DIR" && pwd -P)"

RUNTIME_DIR="$ROOT_DIR/.demo_runtime"
PID_FILE="$RUNTIME_DIR/pids.tsv"
RUNNER_PID_FILE="$RUNTIME_DIR/runner.pid"

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

SERVICE_PATTERNS=(
  "services/market_service/app.py"
  "services/trade_service/app.py"
  "services/opportunity_service/app.py"
  "services/portfolio_service/app.py"
  "services/order_service/app.py"
  "services/execution_service/app.py"
  "mcp_servers/polymarket_server.py"
  "services/hermes_bridge_service/app.py"
  "services/console_api/app.py"
  "bash run_demo.sh"
)

SERVICE_PORTS=(
  "${POLYMARKET_MARKET_SERVICE_PORT:-8020}"
  "${POLYMARKET_TRADE_SERVICE_PORT:-8021}"
  "${POLYMARKET_OPPORTUNITY_SERVICE_PORT:-8022}"
  "${POLYMARKET_PORTFOLIO_SERVICE_PORT:-8023}"
  "${POLYMARKET_ORDER_SERVICE_PORT:-8024}"
  "${POLYMARKET_EXECUTION_SERVICE_PORT:-8025}"
  "${POLYMARKET_MCP_PORT:-9020}"
  "${HERMES_BRIDGE_PORT:-8031}"
  "${CONSOLE_API_PORT:-8030}"
)

is_running() {
  local pid="$1"
  [ -n "${pid:-}" ] && kill -0 "$pid" >/dev/null 2>&1
}

process_in_repo() {
  local pid="$1"
  local cwd=""
  if [ -e "/proc/$pid/cwd" ]; then
    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    [ "$cwd" = "$ROOT_REALPATH" ] || [[ "$cwd" == "$ROOT_REALPATH/"* ]]
    return
  fi
  return 1
}

wait_for_exit() {
  local pid="$1"
  local attempts="${2:-20}"
  local i=0
  while is_running "$pid" && [ "$i" -lt "$attempts" ]; do
    sleep 0.2
    i=$((i + 1))
  done
  ! is_running "$pid"
}

stop_pid() {
  local pid="$1"
  local label="${2:-process}"
  if ! is_running "$pid"; then
    return 0
  fi

  echo "Stopping ${label} (${pid})..."
  kill "$pid" >/dev/null 2>&1 || true
  if ! wait_for_exit "$pid" 20; then
    echo "Force stopping ${label} (${pid})..."
    kill -9 "$pid" >/dev/null 2>&1 || true
    wait_for_exit "$pid" 10 >/dev/null 2>&1 || true
  fi
}

stop_metadata_pids() {
  if [ -f "$PID_FILE" ]; then
    while IFS=$'	' read -r name pid _; do
      [ -n "${pid:-}" ] || continue
      stop_pid "$pid" "$name"
    done < "$PID_FILE"
  fi

  if [ -f "$RUNNER_PID_FILE" ]; then
    local runner_pid=""
    runner_pid="$(cat "$RUNNER_PID_FILE" 2>/dev/null || true)"
    [ -n "${runner_pid:-}" ] && stop_pid "$runner_pid" "runner"
  fi
}

stop_repo_processes() {
  local pattern pid cmd
  for pattern in "${SERVICE_PATTERNS[@]}"; do
    while read -r pid; do
      [ -n "${pid:-}" ] || continue
      [ "$pid" != "$$" ] || continue
      if process_in_repo "$pid"; then
        cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        stop_pid "$pid" "residual ${cmd:-$pattern}"
      fi
    done < <(pgrep -f "$pattern" 2>/dev/null || true)
  done
}

port_pids() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | awk -v port=":$port" '$4 ~ (port "$") {print $0}' | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u
  elif command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
  fi
}

stop_repo_port_processes() {
  local port pid cmd
  for port in "${SERVICE_PORTS[@]}"; do
    while read -r pid; do
      [ -n "${pid:-}" ] || continue
      [ "$pid" != "$$" ] || continue
      if process_in_repo "$pid"; then
        cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
        stop_pid "$pid" "residual port ${port} ${cmd:-process}"
      fi
    done < <(port_pids "$port" || true)
  done
}

print_remaining_ports() {
  local port found=0 lines=""
  for port in "${SERVICE_PORTS[@]}"; do
    if command -v ss >/dev/null 2>&1; then
      lines="$(ss -ltnp 2>/dev/null | awk -v port=":$port" '$4 ~ (port "$") {print $0}' || true)"
    elif command -v lsof >/dev/null 2>&1; then
      lines="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    else
      lines=""
    fi
    if [ -n "$lines" ]; then
      if [ "$found" -eq 0 ]; then
        echo
        echo "Warning: these demo ports are still listening:"
        found=1
      fi
      echo "$lines"
    fi
  done
  [ "$found" -eq 1 ]
}

echo "Stopping clink-polymarket runtime..."
stop_metadata_pids
stop_repo_processes
stop_repo_port_processes

rm -f "$PID_FILE" "$RUNNER_PID_FILE"

if print_remaining_ports; then
  echo "Stopped clink-polymarket runtime. Some ports are still occupied; inspect the warnings above."
else
  echo "Stopped clink-polymarket runtime. Demo ports are clear."
fi
