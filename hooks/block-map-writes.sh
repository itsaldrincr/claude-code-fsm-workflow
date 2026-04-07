#!/bin/bash
# PreToolUse hook: block MAP.md writes from disallowed agents.
# Allowed: orchestrator (empty agent_type), task-planner, session-closer.
# Blocked: every other subagent.
# Output: JSON with permissionDecision=deny + compact XML reason.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
AGENT=$(echo "$INPUT" | jq -r '.agent_type // empty')

# Only act on Write/Edit
case "$TOOL" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

# Only act on MAP.md (basename match — works regardless of path)
[[ "$(basename "$FILE")" != "MAP.md" ]] && exit 0

# Allowed callers
case "$AGENT" in
  ""|task-planner|session-closer) exit 0 ;;
esac

# Block — emit compact XML reason
cat <<EOF
{
  "permissionDecision": "deny",
  "permissionDecisionReason": "<blocked rule=\"map-write-authority\"><by>$AGENT</by><allowed>task-planner, session-closer, orchestrator</allowed><fix>Update task file Registers; orchestrator reflects to MAP.md</fix></blocked>"
}
EOF
exit 0
