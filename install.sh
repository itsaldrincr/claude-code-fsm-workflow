#!/bin/bash
# FSM Workflow installer — idempotent.
# Installs agents, hooks, slash commands, and project templates into ~/.claude/.
# Merges hook registrations into ~/.claude/settings.json without clobbering
# existing user config. Safe to run multiple times.

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "FSM Workflow installer"
echo "======================"
echo ""

# --- 1. Dependency checks ---
command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is required. Install it first:"
  echo "  macOS:  brew install jq"
  echo "  Linux:  sudo apt install jq   (or your distro's equivalent)"
  exit 1
}

if [ ! -d "$CLAUDE_DIR" ]; then
  echo "ERROR: $CLAUDE_DIR not found."
  echo "Install Claude Code first: https://docs.claude.com/en/docs/claude-code"
  exit 1
fi

# --- 2. Back up existing settings ---
if [ -f "$CLAUDE_DIR/settings.json" ]; then
  BACKUP="$CLAUDE_DIR/settings.json.bak.$(date +%s)"
  cp "$CLAUDE_DIR/settings.json" "$BACKUP"
  echo "Backed up existing settings.json → $BACKUP"
else
  echo '{}' > "$CLAUDE_DIR/settings.json"
  echo "Created new settings.json (none existed)"
fi

# --- 3. Copy files ---
mkdir -p "$CLAUDE_DIR/agents" \
         "$CLAUDE_DIR/hooks" \
         "$CLAUDE_DIR/commands" \
         "$CLAUDE_DIR/templates/hooks"

cp "$SCRIPT_DIR"/agents/*.md               "$CLAUDE_DIR/agents/"
cp "$SCRIPT_DIR"/hooks/*.sh                "$CLAUDE_DIR/hooks/"
cp "$SCRIPT_DIR"/commands/*.md             "$CLAUDE_DIR/commands/"
cp "$SCRIPT_DIR"/templates/CLAUDE.md       "$CLAUDE_DIR/templates/"
cp "$SCRIPT_DIR"/templates/settings.json   "$CLAUDE_DIR/templates/"
cp "$SCRIPT_DIR"/templates/hooks/discipline-gate.sh "$CLAUDE_DIR/templates/hooks/"

chmod +x "$CLAUDE_DIR/hooks/"*.sh
chmod +x "$CLAUDE_DIR/templates/hooks/discipline-gate.sh"

AGENT_COUNT=$(ls "$SCRIPT_DIR/agents/" | wc -l | tr -d ' ')
echo "Copied $AGENT_COUNT agents, 4 user-level hooks, 1 slash command, project templates"

# --- 4. Merge hook registrations into settings.json ---
HOOKS_DIR="$CLAUDE_DIR/hooks"

NEW_HOOKS=$(jq -n \
  --arg start "$HOOKS_DIR/surface-map-on-start.sh" \
  --arg mapw  "$HOOKS_DIR/block-map-writes.sh" \
  --arg wread "$HOOKS_DIR/block-worker-reads.sh" \
  --arg model "$HOOKS_DIR/block-model-override.sh" \
  '{
    SessionStart: [
      {hooks: [{type: "command", command: $start}]}
    ],
    PreToolUse: [
      {matcher: "Write|Edit|MultiEdit", hooks: [{type: "command", command: $mapw}]},
      {matcher: "Read",                 hooks: [{type: "command", command: $wread}]},
      {matcher: "Agent",                hooks: [{type: "command", command: $model}]}
    ]
  }')

# Idempotent merge: strip any existing entries whose inner hook commands point
# into our hooks dir, then append the fresh entries.
jq --argjson new "$NEW_HOOKS" --arg hooks_dir "$HOOKS_DIR" '
  .hooks //= {} |
  .hooks.SessionStart = ((.hooks.SessionStart // []) | map(select(
    ((.hooks // []) | map(.command // "") | map(startswith($hooks_dir)) | any) | not
  ))) |
  .hooks.PreToolUse = ((.hooks.PreToolUse // []) | map(select(
    ((.hooks // []) | map(.command // "") | map(startswith($hooks_dir)) | any) | not
  ))) |
  .hooks.SessionStart += $new.SessionStart |
  .hooks.PreToolUse   += $new.PreToolUse
' "$CLAUDE_DIR/settings.json" > "$CLAUDE_DIR/settings.json.tmp"

mv "$CLAUDE_DIR/settings.json.tmp" "$CLAUDE_DIR/settings.json"

# Validate
jq empty "$CLAUDE_DIR/settings.json" || {
  echo "ERROR: settings.json is corrupt after merge."
  if [ -n "${BACKUP:-}" ]; then
    echo "Restore with: cp $BACKUP $CLAUDE_DIR/settings.json"
  fi
  exit 1
}

echo "Merged 4 hook registrations into $CLAUDE_DIR/settings.json"
echo ""
echo "========================================================"
echo "Install complete."
echo "========================================================"
echo ""
echo "To use in any project:"
echo "  1. cd into the project directory"
echo "  2. Open Claude Code there"
echo "  3. Type the slash command: /init-workflow"
echo ""
echo "Then just describe what you want to build. The orchestrator"
echo "will run spec-writer, architect, task-planner, executors,"
echo "auditors, and test-runner automatically."
echo ""
echo "See README.md for full usage notes."
