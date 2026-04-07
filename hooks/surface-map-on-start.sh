#!/bin/bash
# SessionStart hook: if MAP.md exists in CWD, emit a compact status summary.
# Triggers recovery awareness without forcing a full file read.
# Silent no-op if no MAP.md (i.e., not in a workflow project).

[ -f "MAP.md" ] || exit 0

PENDING=$(grep -c '\.\.\. PENDING' MAP.md 2>/dev/null || echo 0)
INPROG=$(grep -c '\.\.\. IN_PROGRESS' MAP.md 2>/dev/null || echo 0)
DONE=$(grep -c '\.\.\. DONE' MAP.md 2>/dev/null || echo 0)

cat <<EOF
<map-status path="MAP.md">
  <counts pending="$PENDING" in_progress="$INPROG" done="$DONE"/>
$(if [ "$INPROG" -gt 0 ]; then echo "  <recovery-needed>IN_PROGRESS tasks present — triage before fresh dispatches</recovery-needed>"; fi)
</map-status>
EOF
exit 0
