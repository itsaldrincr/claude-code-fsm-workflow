#!/bin/bash
# PreToolUse hook: block worker subagents from reading MAP.md or CLAUDE.md.
# Workers must read only their task file + the paths under ## Files → Reads.
# Allowed: orchestrator, dispatcher, task-planner, session-closer, doc-writer,
#          spec-writer, session-handoff (these legitimately need MAP.md/CLAUDE.md).
# Blocked: every other subagent that tries to read either file.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
AGENT=$(echo "$INPUT" | jq -r '.agent_type // empty')

# Only act on Read
[[ "$TOOL" != "Read" ]] && exit 0

# Only act on MAP.md or CLAUDE.md
BASE=$(basename "$FILE")
case "$BASE" in
  MAP.md|CLAUDE.md) ;;
  *) exit 0 ;;
esac

# Allowed callers (orchestrator + planner-tier + bookkeeping agents)
case "$AGENT" in
  ""|dispatcher|task-planner|session-closer|doc-writer|spec-writer|session-handoff) exit 0 ;;
esac

# Block
cat <<EOF
{
  "permissionDecision": "deny",
  "permissionDecisionReason": "<blocked rule=\"worker-read-authority\"><by>$AGENT</by><file>$BASE</file><reason>Workers read only the task file + ## Files paths</reason></blocked>"
}
EOF
exit 0
