# Instructions for Claude Code: Install the FSM Workflow

Paste the entire contents of this file into a fresh Claude Code session. Claude will walk through the install step by step, with safety checks.

---

## Task for Claude

You are installing the **FSM Workflow** for Claude Code on behalf of the user. This package ships a multi-agent pipeline (22 subagents, 4 user-level hooks, 2 slash commands, and project templates) that lives under `~/.claude/`.

The package directory is on the user's machine. **Before you do anything, ask the user for the absolute path to the package directory**. If they don't have it yet, offer to clone fresh:

```bash
git clone https://github.com/itsaldrincr/claude-code-fsm-workflow.git ~/claude-code-fsm-workflow
```

And use `~/claude-code-fsm-workflow` as the package path. Do NOT guess the path.

Once you have the path, follow these steps in order. Stop and report to the user if any step fails.

### Step 0 — Verify the package

Run these checks and report the results:

```bash
PKG=<path the user gave you>
ls "$PKG/install.sh" "$PKG/README.md"
ls "$PKG/plugins/fsm-workflow/agents/" | wc -l      # should be 22
ls "$PKG/hooks/" | wc -l                            # should be 4
ls "$PKG/plugins/fsm-workflow/commands/" | wc -l    # should be 2
ls "$PKG/plugins/fsm-workflow/templates/"           # should show CLAUDE.md, settings.json, hooks/
ls "$PKG/.claude-plugin/marketplace.json"           # marketplace manifest
```

If any of those fail, the package is incomplete or the path is wrong — stop and tell the user.

### Step 1 — Verify dependencies

```bash
command -v jq && jq --version
test -d "$HOME/.claude" && echo "claude dir ok"
```

- If `jq` is missing: tell the user to `brew install jq` (macOS) or `sudo apt install jq` (Linux), then re-run this install prompt.
- If `~/.claude/` is missing: the user doesn't have Claude Code installed yet. Point them at https://docs.claude.com/en/docs/claude-code and stop.

### Step 2 — Preview what's about to happen

Before running the installer, report to the user:

> I'm about to install:
> - 22 agent definitions into `~/.claude/agents/`
> - 4 hook scripts into `~/.claude/hooks/`
> - 1 slash command into `~/.claude/commands/`
> - project templates into `~/.claude/templates/`
>
> I will also merge 4 hook registrations into `~/.claude/settings.json`. Your existing settings, MCP servers, and unrelated hooks will be preserved. A backup will be written to `~/.claude/settings.json.bak.<timestamp>` before any changes.
>
> Proceed?

Wait for the user to confirm. Do not proceed without explicit approval — this modifies their global Claude Code config.

### Step 3 — Run the installer

```bash
cd "$PKG"
./install.sh
```

The installer is idempotent and prints its progress. Capture the full output and relay it to the user.

### Step 4 — Validate the install

Run these checks:

```bash
ls "$HOME/.claude/agents/" | wc -l                         # expect 22 or more (if user had existing agents)
ls "$HOME/.claude/hooks/" | grep -E "block-map-writes|block-worker-reads|block-model-override|surface-map-on-start" | wc -l   # expect 4
ls "$HOME/.claude/commands/init-workflow.md"              # should exist
ls "$HOME/.claude/templates/CLAUDE.md"                    # should exist
ls "$HOME/.claude/templates/hooks/discipline-gate.sh"     # should exist and be executable

# Validate settings.json is well-formed and contains the new hook entries
jq '.hooks.SessionStart, .hooks.PreToolUse' "$HOME/.claude/settings.json"
```

The last `jq` command should show the registered hook entries with absolute paths pointing into `~/.claude/hooks/`. If any of those checks fail, tell the user which one and stop — do not try to fix it yourself without confirming with the user.

### Step 5 — Tell the user what to do next

Report:

> Install complete. To use the workflow:
>
> 1. **Close and re-open Claude Code** so it picks up the new agents, hooks, and the `/init-workflow` slash command.
> 2. `cd` into any project directory.
> 3. Open Claude Code there.
> 4. Type `/init-workflow` to bootstrap that project (installs `CLAUDE.md`, project-local `.claude/settings.json`, and the discipline gate into the project).
> 5. Describe what you want to build. The orchestrator will take it from there.
>
> Full usage notes are in `README.md` inside the package directory.

### Important rules while installing

- **Do NOT** modify any file in the package directory — it's the source of truth.
- **Do NOT** edit `~/.claude/settings.json` by hand. The installer uses `jq` to merge atomically. If you think the installer is wrong, report the issue to the user rather than patching around it.
- **Do NOT** run `install.sh` with `sudo`. Everything should land under `$HOME`.
- **Do NOT** delete the `settings.json.bak.*` file the installer creates. The user may need it to recover.
- **Do NOT** make any changes to the user's existing agents, hooks, or commands that are not part of this package. The installer overwrites files with the same names only — if the user already has, e.g., a custom `fsm-executor.md`, the installer will replace it. **Warn the user about this before running Step 3** if you see any name collisions between `$PKG/agents/` and `$HOME/.claude/agents/`.
- **Do NOT** proceed past any failed check. Stop, report, ask.

### If something goes wrong

The installer creates a backup of `settings.json` before modifying it. To roll back:

```bash
ls "$HOME/.claude/settings.json.bak."*       # find the most recent
cp "$HOME/.claude/settings.json.bak.<timestamp>" "$HOME/.claude/settings.json"
```

To fully uninstall, see the **Uninstall** section in `README.md`.

---

## End of instructions for Claude

That's the full install procedure. When you paste this into Claude Code, Claude will execute it step by step, stopping to confirm before any destructive action.
