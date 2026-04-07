#!/bin/bash
# PreToolUse hook: block Agent calls that override the subagent's frontmatter model.
# Each agent's model is fixed in ~/.claude/agents/<name>.md (opus/sonnet/haiku).
# Forcing a weaker model (e.g. haiku on fsm-executor) caused quality regressions.
# No overrides allowed — let the agent definition decide.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // empty')
SUBAGENT=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty')

# Only act on Agent tool
[[ "$TOOL" != "Agent" ]] && exit 0

# Allow if no model override specified
[ -z "$MODEL" ] && exit 0

# Block — model override attempted
cat <<EOF
{
  "permissionDecision": "deny",
  "permissionDecisionReason": "<blocked rule=\"model-override-forbidden\"><subagent>$SUBAGENT</subagent><attempted>$MODEL</attempted><reason>Agent model is locked by its frontmatter. Drop the model parameter and let the agent definition decide.</reason></blocked>"
}
EOF
exit 0
