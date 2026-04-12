#!/usr/bin/env bash
# orchestrate_monitor.sh — persistent shell loop that drives scripts/orchestrate.py
# and emits state-count changes on stdout. Invoked via Claude Code's Monitor tool.
#
# Exit-code contract (from scripts/orchestrate.py):
#   0 = all done         — pipeline complete, exit monitor
#   1 = action taken     — cycle dispatched work, continue
#   2 = waiting          — cycle had no work to do, continue
#   3 = blocked          — advisor BLOCKED after 3 REVISE rounds, exit monitor
#   4 = unrecoverable    — error, exit monitor
#   5 = audit failed     — deterministic audit gate failed, exit monitor
#
# Flags:
#   --dry-run   — print the command that would run, then exit 0 without looping.

set -euo pipefail

if [ "${1:-}" = "--dry-run" ]; then
  echo "dry-run: would invoke loop: PYTHONPATH=. python3 scripts/orchestrate.py"
  exit 0
fi

while true; do
  set +e
  PYTHONPATH=. python3 scripts/orchestrate.py
  rc=$?
  set -e
  case "${rc}" in
    0) echo "[$(date +%H:%M:%S)] orchestrate exit 0 — pipeline complete"; exit 0 ;;
    1) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=1 (action taken)" ;;
    2) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=2 (waiting)" ;;
    3) echo "[$(date +%H:%M:%S)] orchestrate exit 3 — BLOCKED"; exit 3 ;;
    4) echo "[$(date +%H:%M:%S)] orchestrate exit 4 — ERROR"; exit 4 ;;
    5) echo "[$(date +%H:%M:%S)] orchestrate exit 5 — AUDIT FAILED"; exit 5 ;;
    *) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=${rc} (unexpected)"; exit "${rc}" ;;
  esac
  sleep 2
done
