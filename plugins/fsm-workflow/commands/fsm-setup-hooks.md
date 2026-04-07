---
description: Install the FSM workflow enforcement hooks. Required after marketplace install for the full package — without these hooks the workflow loses context isolation, single-writer state, nonce-proof reads, and the discipline gate.
---

The user just ran `/plugin install fsm-workflow` from the Claude Code plugin marketplace and is invoking this command to complete the install. The plugin marketplace ships agents, commands, and templates — but **not** hooks. The hooks are the entire moat of this package. Without them, it's 22 persona agents with no teeth.

Your job is to get the four user-level hooks into `~/.claude/hooks/` and registered in `~/.claude/settings.json`. The package ships an idempotent `install.sh` that does exactly this — your job is to run it (with the user's permission) or walk them through running it themselves.

## Step 1 — check if hooks are already installed

Run:

```bash
ls ~/.claude/hooks/block-map-writes.sh \
   ~/.claude/hooks/block-worker-reads.sh \
   ~/.claude/hooks/block-model-override.sh \
   ~/.claude/hooks/surface-map-on-start.sh 2>&1
```

Also check they're registered in settings.json:

```bash
jq '.hooks.PreToolUse, .hooks.SessionStart' ~/.claude/settings.json
```

If all four files exist AND the settings.json hook arrays reference them → report "enforcement is already active, no action needed" and stop. Do not re-install.

## Step 2 — explain why this extra step exists

If the hooks are missing, explain plainly:

> The Claude Code plugin marketplace installs agents, commands, and templates — but not hooks. This package's entire value proposition is mechanical enforcement via 4 user-level hooks that physically prevent:
>
> - Workers from reading `MAP.md` or `CLAUDE.md` (context isolation)
> - Unauthorized agents from writing `MAP.md` (single-writer state)
> - Agents from overriding each other's model assignments (model lock)
> - Sessions from resuming blind without a status summary (recovery awareness)
>
> Every competing multi-agent package the author surveyed relies on prompt instructions for these properties — none return `permissionDecision: deny` from hooks on anything more substantial than `rm -rf`. This is the moat. Without the hooks, you have the agents but not the enforcement, and the workflow will drift like everyone else's.

## Step 3 — offer the user three paths

**Path A — automatic (with explicit permission).** Offer to clone the repo to a temp dir and run the installer yourself. Do NOT proceed without user confirmation — this modifies global Claude Code config.

If the user says yes:

```bash
TMP=$(mktemp -d)
git clone --quiet --depth 1 https://github.com/itsaldrincr/claude-code-fsm-workflow.git "$TMP/fsm-workflow"
cd "$TMP/fsm-workflow" && ./install.sh
rm -rf "$TMP"
```

**Path B — manual.** Give them the exact commands to run in their own terminal:

```bash
git clone https://github.com/itsaldrincr/claude-code-fsm-workflow.git
cd claude-code-fsm-workflow
./install.sh
```

**Path C — ask another Claude.** Tell them the repo ships an `INSTALL_FOR_CLAUDE.md` file that they can paste into a fresh Claude Code session. Claude will walk them through the install with safety checks.

Let the user pick. Default recommendation: **Path A** (automatic) for users who trust you, **Path B** (manual) for users who want to see the commands themselves.

## Step 4 — validate after install

After Path A or B runs, verify the install landed:

```bash
ls ~/.claude/hooks/{block-map-writes,block-worker-reads,block-model-override,surface-map-on-start}.sh
jq '.hooks.PreToolUse | length, .hooks.SessionStart | length' ~/.claude/settings.json
```

Expected: all four `.sh` files listed, `PreToolUse` length ≥ 3, `SessionStart` length ≥ 1. Report the numbers to the user.

## Step 5 — remind the user to restart

Tell them:

> Close and re-open Claude Code so the new hook registrations take effect. After that, `cd` into any project directory, open Claude Code there, and run `/init-workflow` to bootstrap that project's `CLAUDE.md` + discipline gate. Then describe what you want to build.

## Rules

- **Do NOT run `./install.sh` without explicit user approval** at Step 3. This modifies `~/.claude/settings.json`.
- **Do NOT skip Step 1.** Re-running an idempotent installer is safe but noisy; detecting "already installed" is cleaner UX.
- **Do NOT try to install the hooks manually by copying files or editing settings.json yourself.** The `install.sh` script handles backup, idempotent merge, and validation in ways that are hard to replicate line by line. Trust the installer.
- **Do NOT proceed past a failed dependency check.** If `jq` is missing on the user's system, tell them to `brew install jq` (macOS) or `sudo apt install jq` (Linux) and stop until they confirm it's installed.
- **Do NOT fix the installer if it fails.** Report the error verbatim and stop. The user can open an issue on the repo.
