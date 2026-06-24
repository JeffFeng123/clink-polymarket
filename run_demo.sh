#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="$ROOT_DIR/.demo_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/pids.tsv"
RUNNER_PID_FILE="$RUNTIME_DIR/runner.pid"

SERVICE_PIDS=()

cleanup() {
  if [ "${#SERVICE_PIDS[@]}" -gt 0 ]; then
    echo
    echo "Stopping clink-polymarket services..."
    for pid in "${SERVICE_PIDS[@]}"; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
    done
    wait >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE" "$RUNNER_PID_FILE"
}

trap cleanup EXIT INT TERM

mkdir -p "$LOG_DIR"
: > "$PID_FILE"
echo "$$" > "$RUNNER_PID_FILE"

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

start_service() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/${name}.log"
  echo "Starting ${name}..."
  "$@" >"$log_file" 2>&1 &
  local pid=$!
  SERVICE_PIDS+=("$pid")
  printf "%s\t%s\t%s\n" "$name" "$pid" "$log_file" >> "$PID_FILE"
  sleep 1
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "Failed to start ${name}. Log:"
    cat "$log_file"
    exit 1
  fi
}

start_service "polymarket_market_service" python3 services/market_service/app.py
start_service "polymarket_trade_service" python3 services/trade_service/app.py
start_service "polymarket_opportunity_service" python3 services/opportunity_service/app.py
start_service "polymarket_portfolio_service" python3 services/portfolio_service/app.py
start_service "polymarket_order_service" python3 services/order_service/app.py
start_service "polymarket_mcp_server" python3 mcp_servers/polymarket_server.py

echo
echo "Clink Polymarket public MCP surface is ready."
echo "Run: python3 scripts/polymarket_readonly_smoke.py"
echo "Run: python3 scripts/public_mcp_surface_smoke.py"
echo "Use bash run_demo_stop.sh to stop the backgrounded demo safely."

while true; do
  sleep 5
done
