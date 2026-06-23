#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="$ROOT_DIR/.demo_runtime"
PID_FILE="$RUNTIME_DIR/pids.tsv"
RUNNER_PID_FILE="$RUNTIME_DIR/runner.pid"

stop_pid() {
  local pid="$1"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

if [ -f "$PID_FILE" ]; then
  while IFS=$'\t' read -r name pid _; do
    echo "Stopping ${name} (${pid})..."
    stop_pid "$pid"
  done < "$PID_FILE"
fi

if [ -f "$RUNNER_PID_FILE" ]; then
  runner_pid="$(cat "$RUNNER_PID_FILE" 2>/dev/null || true)"
  echo "Stopping runner (${runner_pid})..."
  stop_pid "$runner_pid"
fi

rm -f "$PID_FILE" "$RUNNER_PID_FILE"
echo "Stopped clink-polymarket runtime."
