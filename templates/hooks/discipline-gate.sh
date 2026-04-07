#!/bin/bash
# PostToolUse hook: discipline gate for Python and TypeScript files.
# Runs after every Edit/Write on .py or .ts files. If the file violates the
# coding discipline rules in CLAUDE.md, the hook returns decision=block with
# a compact XML violation list. The agent reads the violations as feedback
# and fixes them in-file (treats it like a compiler error).
#
# This is a project-level hook installed by doc-writer (pre-workflow mode).
# Place at .claude/hooks/discipline-gate.sh in the project root.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only act on Edit/Write/MultiEdit
case "$TOOL" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

# Only act on Python or TypeScript source files
case "$FILE" in
  *.py|*.ts|*.tsx) ;;
  *) exit 0 ;;
esac

[ ! -f "$FILE" ] && exit 0

# Inline minimal discipline checks. Each emits a <v line=N rule=X>...</v> tag.
VIOLATIONS=""

# Check 1: max 20 lines per function body (Python def, TS function)
# Check 2: max 2 params per function
# Check 3: no print() in Python, no console.log/warn/error in TS
# Check 4: no commented-out code (heuristic: 3+ consecutive comment lines that look like code)
# (Simple heuristics — a real impl would use a Python AST parser or ts-morph)

LINE_NUM=0
while IFS= read -r LINE; do
  LINE_NUM=$((LINE_NUM + 1))

  # Python: print( call
  if [[ "$FILE" == *.py ]] && [[ "$LINE" =~ ^[[:space:]]*print\( ]]; then
    VIOLATIONS+="<v line=\"$LINE_NUM\" rule=\"no-print\">use logging instead of print()</v>"
  fi

  # TS: console.log/warn/error
  if [[ "$FILE" == *.ts || "$FILE" == *.tsx ]] && [[ "$LINE" =~ console\.(log|warn|error) ]]; then
    VIOLATIONS+="<v line=\"$LINE_NUM\" rule=\"no-console\">use createLogger instead of console.*</v>"
  fi
done < "$FILE"

# If no violations, exit clean
[ -z "$VIOLATIONS" ] && exit 0

# Emit block decision with compact XML payload
cat <<EOF
{
  "decision": "block",
  "reason": "<discipline-fail file=\"$FILE\">$VIOLATIONS</discipline-fail>"
}
EOF
exit 0
