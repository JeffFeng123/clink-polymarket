#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="$ROOT_DIR/.demo_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.tsv"
RUNNER_PID_FILE="$RUNTIME_DIR/runner.pid"

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

service_url() {
  case "$1" in
    polymarket_market_service) printf "http://%s:%s" "${POLYMARKET_MARKET_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_MARKET_SERVICE_PORT:-8020}" ;;
    polymarket_trade_service) printf "http://%s:%s" "${POLYMARKET_TRADE_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_TRADE_SERVICE_PORT:-8021}" ;;
    polymarket_opportunity_service) printf "http://%s:%s" "${POLYMARKET_OPPORTUNITY_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_OPPORTUNITY_SERVICE_PORT:-8022}" ;;
    polymarket_portfolio_service) printf "http://%s:%s" "${POLYMARKET_PORTFOLIO_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_PORTFOLIO_SERVICE_PORT:-8023}" ;;
    polymarket_order_service) printf "http://%s:%s" "${POLYMARKET_ORDER_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_ORDER_SERVICE_PORT:-8024}" ;;
    polymarket_execution_service) printf "http://%s:%s" "${POLYMARKET_EXECUTION_SERVICE_HOST:-127.0.0.1}" "${POLYMARKET_EXECUTION_SERVICE_PORT:-8025}" ;;
    polymarket_mcp_server) printf "http://%s:%s/mcp/" "${POLYMARKET_MCP_HOST:-127.0.0.1}" "${POLYMARKET_MCP_PORT:-9020}" ;;
    clink_hermes_console) printf "http://%s:%s" "${CONSOLE_API_HOST:-0.0.0.0}" "${CONSOLE_API_PORT:-8030}" ;;
    *) printf "-" ;;
  esac
}

print_line() {
  printf "%-32s %-12s %-8s %-50s %s\n" "$1" "$2" "$3" "$4" "$5"
}

echo "Clink Polymarket runtime status"
echo
if [ -f "$RUNNER_PID_FILE" ]; then
  runner_pid="$(cat "$RUNNER_PID_FILE" 2>/dev/null || true)"
  if [ -n "$runner_pid" ] && kill -0 "$runner_pid" >/dev/null 2>&1; then
    echo "Runner: running (${runner_pid})"
  else
    echo "Runner: stale metadata (${runner_pid:-unknown})"
  fi
else
  echo "Runner: not running"
fi

echo
print_line "Service" "Status" "PID" "URL" "Log"
print_line "-------" "------" "---" "---" "---"

if [ -f "$PID_FILE" ]; then
  while IFS=$'\t' read -r name pid log_file; do
    status="stopped"
    if [ -n "${pid:-}" ] && kill -0 "$pid" >/dev/null 2>&1; then
      status="running"
    fi
    print_line "$name" "$status" "${pid:-"-"}" "$(service_url "$name")" "${log_file:-"-"}"
  done < "$PID_FILE"
else
  echo "No PID metadata found. Start with bash run_demo.sh"
fi

if [ -d "$LOG_DIR" ]; then
  echo
  echo "Log files:"
  find "$LOG_DIR" -maxdepth 1 -type f | sort
fi
