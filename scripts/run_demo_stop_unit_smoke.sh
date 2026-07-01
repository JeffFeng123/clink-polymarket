#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p services/market_service .demo_runtime
python3 -c 'import time; time.sleep(120)' services/market_service/app.py >/tmp/clink_stop_fake.log 2>&1 &
fake_pid=$!
printf "polymarket_market_service\t%s\t/tmp/clink_stop_fake.log\n" "$fake_pid" > .demo_runtime/pids.tsv

test_running() { kill -0 "$fake_pid" >/dev/null 2>&1; }
if ! test_running; then
  echo "fake service did not start" >&2
  exit 1
fi

bash run_demo_stop.sh >/tmp/clink_stop_smoke.log 2>&1 || {
  cat /tmp/clink_stop_smoke.log
  exit 1
}

if test_running; then
  echo "fake service still running after stop" >&2
  kill "$fake_pid" >/dev/null 2>&1 || true
  cat /tmp/clink_stop_smoke.log
  exit 1
fi

cat /tmp/clink_stop_smoke.log
