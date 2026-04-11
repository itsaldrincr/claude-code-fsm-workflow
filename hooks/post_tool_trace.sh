#!/usr/bin/env bash
# PostToolUse hook for fsm-trace: pipes the hook event JSON on stdin to
# fsm_core/trace.py which appends a JSONL trace event to the per-session log.
set -euo pipefail
python3 "$(dirname "$0")/fsm_core/trace.py"
exit 0
