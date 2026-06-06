#!/usr/bin/env bash
#
# dev.sh — launch every local surface in one terminal.
#
# Starts three independent processes and streams their logs into this
# terminal with a per-process prefix so you can tell them apart:
#
#   [api]  uv run finance serve          REST + MCP on :8000
#   [web]  npm run dev (Vite)            web UI on :5173 (proxies /api -> :8000)
#   [bot]  uv run finance bot            Telegram long-poller
#
# Ctrl-C tears down all three. If any one exits on its own, the whole
# group is brought down so a silent crash doesn't go unnoticed.
#
# Usage:
#   scripts/dev.sh            # API + web (dev/hot-reload) + bot
#   scripts/dev.sh --no-bot   # skip the Telegram poller
#
set -euo pipefail

cd "$(dirname "$0")/.."

RUN_BOT=1
for arg in "$@"; do
  case "$arg" in
    --no-bot) RUN_BOT=0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

pids=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "[dev] shutting down…"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Prefix each line of a stream with a tag, e.g. [api].
run() {
  local tag="$1"; shift
  "$@" 2>&1 | sed -u "s/^/[$tag] /" &
  pids+=("$!")
}

run api uv run finance serve
run web npm --prefix src/finance/web run dev
if [[ "$RUN_BOT" == "1" ]]; then
  run bot uv run finance bot
fi

# Exit (and trigger cleanup) as soon as any child exits.
wait -n
