#!/usr/bin/env bash
# orchestrate_monitor.sh — persistent shell loop that drives scripts/orchestrate.py
# and emits state-count changes on stdout. Invoked via Claude Code's Monitor tool.
#
# Exit-code contract (from scripts/orchestrate.py):
#   0 = all done         — pipeline complete, exit monitor
#   1 = action taken     — cycle dispatched work, continue
#   2 = waiting          — cycle had no work to do, continue (cycle cadence)
#   3 = blocked          — advisor BLOCKED after 3 REVISE rounds, exit monitor
#   4 = unrecoverable    — error, exit monitor
#
# Flags:
#   --dry-run   — print the command that would run, then exit 0 without looping.

set -u

MONITOR_POLL_SECONDS="${MONITOR_POLL_SECONDS:-20}"
ORCHESTRATE_CMD="PYTHONPATH=. python3 scripts/orchestrate.py"
ORCHESTRATE_LOG="/tmp/orch-last.log"

if [ "${1:-}" = "--dry-run" ]; then
  echo "dry-run: would loop invoking: ${ORCHESTRATE_CMD}"
  echo "dry-run: poll cadence: ${MONITOR_POLL_SECONDS}s"
  exit 0
fi

prev_state=""

emit_state_change() {
  local curr
  curr=$(python3 -c "
import re
from collections import Counter
try:
    with open('MAP.md') as f:
        content = f.read()
except FileNotFoundError:
    print('MAP_MISSING'); exit()
states = re.findall(r'\.\.+\s*(PENDING|IN_PROGRESS|EXECUTING|VERIFY|DONE|REVIEW|BLOCKED|FAILED|PARTIAL)', content)
c = Counter(states)
parts = [f'{k}={v}' for k in ('PENDING','IN_PROGRESS','REVIEW','DONE','BLOCKED','FAILED') if c.get(k,0)>0]
print(' '.join(parts) if parts else 'empty')
" 2>/dev/null)
  if [ "${curr}" != "${prev_state}" ]; then
    echo "[$(date +%H:%M:%S)] ${curr}"
    prev_state="${curr}"
  fi
}

while true; do
  emit_state_change
  if ! pgrep -f "scripts/orchestrate.py" > /dev/null 2>&1; then
    eval "${ORCHESTRATE_CMD}" > "${ORCHESTRATE_LOG}" 2>&1
    rc=$?
    case "${rc}" in
      0) echo "[$(date +%H:%M:%S)] orchestrate exit 0 — pipeline complete"; exit 0 ;;
      1) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=1 (action taken)" ;;
      2) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=2 (waiting)" ;;
      3) echo "[$(date +%H:%M:%S)] orchestrate exit 3 — BLOCKED"; exit 3 ;;
      4) echo "[$(date +%H:%M:%S)] orchestrate exit 4 — ERROR (see ${ORCHESTRATE_LOG})"; exit 4 ;;
      *) echo "[$(date +%H:%M:%S)] orchestrate cycle rc=${rc} (unexpected)" ;;
    esac
  fi
  sleep "${MONITOR_POLL_SECONDS}"
done
