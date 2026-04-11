#!/usr/bin/env bash
# Idempotent installer for the claude-harness.
# Copies hooks, agent definitions, and fsm_core modules into ~/.claude/.
# Merges hook entries into ~/.claude/settings.json via jq, creating a
# timestamped backup on every run.

set -euo pipefail

# ── names + paths ──────────────────────────────────────────────────────────────
readonly HOOK_PRE_READ="pre_read.py"
readonly HOOK_POST_READ="post_read.py"
readonly HOOK_POST_GREP="post_grep.py"
readonly HOOK_POST_EDIT="post_edit.py"
readonly HOOK_SESSION_START="session_start.py"
readonly HOOK_STOP="stop.py"

readonly SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly TARGET_DIR="$HOME/.claude/hooks/repo-map"
readonly SETTINGS="$HOME/.claude/settings.json"
trap 'rm -f "$SETTINGS.tmp"' EXIT
readonly INSTALLED_PREFIX="$HOME/.claude/hooks/repo-map/src/repo_map/hooks"

readonly HOOK_POST_TOOL_TRACE="post_tool_trace.sh"
readonly TRACE_HOOK_SOURCE_DIR="$SOURCE_DIR/hooks"
readonly TRACE_HOOK_TARGET_DIR="$HOME/.claude/hooks/fsm-trace"
readonly FSM_CORE_SOURCE_DIR="$SOURCE_DIR/src/fsm_core"
readonly FSM_CORE_TARGET_DIR="$HOME/.claude/hooks/fsm-trace/fsm_core"

readonly ENFORCEMENT_HOOK_SOURCE_DIR="$SOURCE_DIR/hooks"
readonly ENFORCEMENT_HOOK_TARGET_DIR="$HOME/.claude/hooks"
readonly HOOK_BLOCK_MAP_WRITES="block-map-writes.sh"
readonly HOOK_BLOCK_WORKER_READS="block-worker-reads.sh"
readonly HOOK_BLOCK_MODEL_OVERRIDE="block-model-override.sh"
readonly HOOK_SURFACE_MAP_ON_START="surface-map-on-start.sh"

# ── preflight ──────────────────────────────────────────────────────────────────
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not installed. Install via 'brew install jq' or your package manager." >&2
    exit 1
fi

if [ ! -d "$SOURCE_DIR/src/repo_map" ]; then
    echo "ERROR: source tree not found at $SOURCE_DIR/src/repo_map" >&2
    exit 1
fi

# ── copy python tree ───────────────────────────────────────────────────────────
mkdir -p "$TARGET_DIR"
mkdir -p "$TARGET_DIR/log"
cp -R "$SOURCE_DIR/src" "$TARGET_DIR/"
find "$TARGET_DIR" -name "*.py" -type f -exec chmod +x {} \;

# ── copy fsm-trace hook + fsm_core python tree ────────────────────────────────
if [ -d "$FSM_CORE_SOURCE_DIR" ]; then
    mkdir -p "$TRACE_HOOK_TARGET_DIR"
    mkdir -p "$FSM_CORE_TARGET_DIR"
    cp "$TRACE_HOOK_SOURCE_DIR/$HOOK_POST_TOOL_TRACE" "$TRACE_HOOK_TARGET_DIR/"
    chmod +x "$TRACE_HOOK_TARGET_DIR/$HOOK_POST_TOOL_TRACE"
    cp "$FSM_CORE_SOURCE_DIR/trace.py" "$FSM_CORE_TARGET_DIR/"
    cp "$FSM_CORE_SOURCE_DIR/__init__.py" "$FSM_CORE_TARGET_DIR/"
fi

# ── copy pipeline-enforce hooks ────────────────────────────────────────────────
PIPELINE_ENFORCE_SOURCE_DIR="$SOURCE_DIR/hooks"
PIPELINE_ENFORCE_TARGET_DIR="$HOME/.claude/hooks/pipeline-enforce"
mkdir -p "$PIPELINE_ENFORCE_TARGET_DIR"
cp "$PIPELINE_ENFORCE_SOURCE_DIR/validate_map_transition.py" "$PIPELINE_ENFORCE_TARGET_DIR/"
cp "$PIPELINE_ENFORCE_SOURCE_DIR/nudge_orchestrate.py" "$PIPELINE_ENFORCE_TARGET_DIR/"
chmod +x "$PIPELINE_ENFORCE_TARGET_DIR/validate_map_transition.py"
chmod +x "$PIPELINE_ENFORCE_TARGET_DIR/nudge_orchestrate.py"

# ── copy top-level enforcement hooks (block-*/surface-*) ──────────────────────
# These are the four hooks the plugin-marketplace README and /fsm-setup-hooks
# command advertise as the moat. They live at $HOME/.claude/hooks/ (top level),
# not in a subdirectory, so they can be referenced directly in settings.json.
mkdir -p "$ENFORCEMENT_HOOK_TARGET_DIR"
for hook in "$HOOK_BLOCK_MAP_WRITES" "$HOOK_BLOCK_WORKER_READS" "$HOOK_BLOCK_MODEL_OVERRIDE" "$HOOK_SURFACE_MAP_ON_START"; do
    cp "$ENFORCEMENT_HOOK_SOURCE_DIR/$hook" "$ENFORCEMENT_HOOK_TARGET_DIR/"
    chmod +x "$ENFORCEMENT_HOOK_TARGET_DIR/$hook"
done

# ── copy agent definitions ─────────────────────────────────────────────────────
# Agents live under plugins/fsm-workflow/agents/ (the Claude Code plugin layout).
# Fall back to top-level agents/ for older repo layouts.
AGENTS_SOURCE_DIR="$SOURCE_DIR/plugins/fsm-workflow/agents"
if [ ! -d "$AGENTS_SOURCE_DIR" ] && [ -d "$SOURCE_DIR/agents" ]; then
    AGENTS_SOURCE_DIR="$SOURCE_DIR/agents"
fi
AGENTS_TARGET_DIR="$HOME/.claude/agents"
if [ -d "$AGENTS_SOURCE_DIR" ]; then
    mkdir -p "$AGENTS_TARGET_DIR"
    for agent_file in "$AGENTS_SOURCE_DIR"/*.md; do
        [ -f "$agent_file" ] && cp "$agent_file" "$AGENTS_TARGET_DIR/"
    done
fi

# ── copy slash commands ───────────────────────────────────────────────────────
# Slash commands live in plugins/fsm-workflow/commands/. Direct-clone installs
# copy them to ~/.claude/commands/ so /init-workflow and /fsm-setup-hooks are
# usable without going through the plugin marketplace.
COMMANDS_SOURCE_DIR="$SOURCE_DIR/plugins/fsm-workflow/commands"
COMMANDS_TARGET_DIR="$HOME/.claude/commands"
if [ -d "$COMMANDS_SOURCE_DIR" ]; then
    mkdir -p "$COMMANDS_TARGET_DIR"
    for cmd_file in "$COMMANDS_SOURCE_DIR"/*.md; do
        [ -f "$cmd_file" ] && cp "$cmd_file" "$COMMANDS_TARGET_DIR/"
    done
fi

# ── copy project templates ────────────────────────────────────────────────────
# /init-workflow reads these templates when bootstrapping a fresh project's
# CLAUDE.md + discipline gate. Copied to ~/.claude/templates/ so the slash
# command can find them without knowing the repo path.
TEMPLATES_SOURCE_DIR="$SOURCE_DIR/plugins/fsm-workflow/templates"
TEMPLATES_TARGET_DIR="$HOME/.claude/templates"
if [ -d "$TEMPLATES_SOURCE_DIR" ]; then
    mkdir -p "$TEMPLATES_TARGET_DIR"
    cp -R "$TEMPLATES_SOURCE_DIR"/. "$TEMPLATES_TARGET_DIR/"
    find "$TEMPLATES_TARGET_DIR/hooks" -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
fi

# ── copy orchestrator + audit scripts ─────────────────────────────────────────
# scripts/orchestrate.py, atomize_task.py, audit_discipline.py, check_deps.py,
# session_close.py need to be reachable from a known location so /init-workflow
# can copy them into each new project without hardcoding the repo path.
SCRIPTS_SOURCE_DIR="$SOURCE_DIR/scripts"
SCRIPTS_TARGET_DIR="$HOME/.claude/scripts"
if [ -d "$SCRIPTS_SOURCE_DIR" ]; then
    mkdir -p "$SCRIPTS_TARGET_DIR"
    for script_file in "$SCRIPTS_SOURCE_DIR"/*.py; do
        [ -f "$script_file" ] && cp "$script_file" "$SCRIPTS_TARGET_DIR/"
    done
    find "$SCRIPTS_TARGET_DIR" -type f -name "*.py" -exec chmod +x {} \;
fi

# ── ensure settings.json exists ────────────────────────────────────────────────
mkdir -p "$(dirname "$SETTINGS")"
if [ ! -f "$SETTINGS" ]; then
    echo '{"hooks": {}}' > "$SETTINGS"
fi

# ── backup on every run (acceptance #7) ────────────────────────────────────────
readonly TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
readonly BACKUP="$SETTINGS.bak.$TIMESTAMP"
cp "$SETTINGS" "$BACKUP"

# ── merge hook entries via jq ──────────────────────────────────────────────────
# Args: $1=event  $2=matcher (empty string = no matcher)  $3=command
# Idempotent: skips exact duplicates; stacks onto an existing (event, matcher)
# entry if one exists, else creates a new entry.
_merge_hook_entry() {
    local event="$1"
    local matcher="$2"
    local command="$3"

    local already_present
    already_present=$(jq --arg ev "$event" --arg mt "$matcher" --arg cmd "$command" '
        (.hooks[$ev] // [])
        | map(select(((.matcher // "") == $mt) and
                     ((.hooks // []) | map(.command) | index($cmd) != null)))
        | length
    ' "$SETTINGS")

    if [ "$already_present" -gt 0 ]; then
        skipped_count=$((skipped_count + 1))
        return 0
    fi

    jq --arg ev "$event" --arg mt "$matcher" --arg cmd "$command" '
        .hooks //= {}
        | .hooks[$ev] //= []
        | (.hooks[$ev] | map(((.matcher // "") == $mt)) | index(true)) as $idx
        | if $idx == null then
            .hooks[$ev] += [
              (if $mt == "" then {} else {matcher: $mt} end)
              + {"hooks": [{"type": "command", "command": $cmd}]}
            ]
          else
            .hooks[$ev][$idx].hooks += [{"type": "command", "command": $cmd}]
          end
    ' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"

    added_count=$((added_count + 1))
}

added_count=0
skipped_count=0

# ── merge repo-map hook entries ────────────────────────────────────────────────
_merge_hook_entry "PreToolUse"   "Read"                  "$INSTALLED_PREFIX/$HOOK_PRE_READ"
_merge_hook_entry "PostToolUse"  "Read"                  "$INSTALLED_PREFIX/$HOOK_POST_READ"
_merge_hook_entry "PostToolUse"  "Grep"                  "$INSTALLED_PREFIX/$HOOK_POST_GREP"
_merge_hook_entry "PostToolUse"  "Edit|Write|MultiEdit"  "$INSTALLED_PREFIX/$HOOK_POST_EDIT"
_merge_hook_entry "SessionStart" ""                      "$INSTALLED_PREFIX/$HOOK_SESSION_START"
_merge_hook_entry "Stop"         ""                      "$INSTALLED_PREFIX/$HOOK_STOP"

# ── merge fsm-trace hook entry ─────────────────────────────────────────────────
_merge_hook_entry "PostToolUse"  ""                      "$TRACE_HOOK_TARGET_DIR/$HOOK_POST_TOOL_TRACE"

# ── merge pipeline-enforce hook entries ────────────────────────────────────────
_merge_hook_entry "PreToolUse"   "Edit"                  "$PIPELINE_ENFORCE_TARGET_DIR/validate_map_transition.py"
_merge_hook_entry "PostToolUse"  "Read"                  "$PIPELINE_ENFORCE_TARGET_DIR/nudge_orchestrate.py"

# ── merge top-level enforcement hook entries ──────────────────────────────────
_merge_hook_entry "PreToolUse"   "Write|Edit|MultiEdit"  "$ENFORCEMENT_HOOK_TARGET_DIR/$HOOK_BLOCK_MAP_WRITES"
_merge_hook_entry "PreToolUse"   "Read"                  "$ENFORCEMENT_HOOK_TARGET_DIR/$HOOK_BLOCK_WORKER_READS"
_merge_hook_entry "PreToolUse"   "Agent"                 "$ENFORCEMENT_HOOK_TARGET_DIR/$HOOK_BLOCK_MODEL_OVERRIDE"
_merge_hook_entry "SessionStart" ""                      "$ENFORCEMENT_HOOK_TARGET_DIR/$HOOK_SURFACE_MAP_ON_START"

# ── summary ────────────────────────────────────────────────────────────────────
echo "repo-map installer summary:"
echo "  source:    $SOURCE_DIR/src/repo_map/"
echo "  target:    $TARGET_DIR/"
echo "  settings:  $SETTINGS"
echo "  backup:    $BACKUP"
echo "  added:     $added_count"
echo "  skipped:   $skipped_count (already present)"
echo "  fsm-trace target: $TRACE_HOOK_TARGET_DIR/"
echo "  fsm_core target:  $FSM_CORE_TARGET_DIR/"
echo "  agents target:    $AGENTS_TARGET_DIR/"
echo "  commands target:  $COMMANDS_TARGET_DIR/"
echo "  templates target: $TEMPLATES_TARGET_DIR/"
echo "  scripts target:   $SCRIPTS_TARGET_DIR/"
echo "  enforcement:      $ENFORCEMENT_HOOK_TARGET_DIR/{block-*,surface-*}.sh"
