# FSM Workflow for Claude Code

A multi-agent finite-state-machine workflow that turns Claude Code into an autonomous engineering pipeline. Brainstorm → spec → architect → plan → execute → audit → test → close, with mechanical enforcement via hooks so agents can't drift off the rails.

## What this is

Claude Code already supports subagents. This package wires 22 of them together into a disciplined pipeline with:

- **Strict role separation** — orchestrator never writes code; workers never write the task map; auditors never fix bugs. Enforced by hooks, not vibes.
- **Stateless workers** — every FSM executor reads everything from disk on each turn. No conversation memory means no drift across context compactions.
- **Nonce-proof reads** — each task file carries a checkpoint hex string. Workers must echo the current nonce in their Registers update, proving they actually read the file.
- **Discipline gate** — every `.py` / `.ts` write is post-processed by a hook that blocks on coding-discipline violations. The agent treats the block as a compiler error and fixes in-loop.
- **Brainstorming mode + auto pipeline** — you talk to the orchestrator about what you want. It captures specs, runs research, dispatches the architect, plans tasks, runs executors in waves, audits, tests, and closes out — all without you babysitting.

Read `templates/CLAUDE.md` for the full SOP. It's the source of truth for how the workflow runs; the agents and hooks are just the mechanical enforcement of what's written there.

## What's in this package

```
fsm-workflow/
├── README.md                     # this file
├── install.sh                    # idempotent installer
├── INSTALL_FOR_CLAUDE.md         # paste-ready prompt for another Claude to install
├── agents/                       # 22 subagent definitions → ~/.claude/agents/
│   ├── architect.md
│   ├── bug-scanner.md
│   ├── code-auditor.md
│   ├── code-fixer.md
│   ├── code-reviewer.md
│   ├── debugger.md
│   ├── dep-checker.md
│   ├── dispatcher.md
│   ├── doc-writer.md
│   ├── explore-scout.md
│   ├── explore-superscout.md
│   ├── file-lister.md
│   ├── fsm-executor.md
│   ├── fsm-integrator.md
│   ├── mock-server.md
│   ├── mockup-verifier.md
│   ├── research-scout.md
│   ├── session-closer.md
│   ├── session-handoff.md
│   ├── spec-writer.md
│   ├── task-planner.md
│   └── test-runner.md
├── hooks/                        # user-level hooks → ~/.claude/hooks/
│   ├── block-map-writes.sh       # only task-planner + session-closer may touch MAP.md
│   ├── block-worker-reads.sh     # workers can't read MAP.md / CLAUDE.md (enforces context isolation)
│   ├── block-model-override.sh   # stops callers from forcing a weaker model on an agent
│   └── surface-map-on-start.sh   # SessionStart: prints MAP.md status summary for recovery awareness
├── commands/
│   └── init-workflow.md          # /init-workflow slash command → ~/.claude/commands/
└── templates/                    # project scaffold → ~/.claude/templates/
    ├── CLAUDE.md                 # full workflow SOP (coding discipline + task coordination)
    ├── settings.json             # project-level settings with discipline gate registered
    └── hooks/
        └── discipline-gate.sh    # PostToolUse hook: blocks .py/.ts writes with violations
```

## Dependencies

- **Claude Code** installed and working. https://docs.claude.com/en/docs/claude-code
- **jq** — the installer uses it to merge hook registrations into your existing `settings.json` without clobbering it.
  - macOS: `brew install jq`
  - Linux: `sudo apt install jq` (or your distro's equivalent)
- **bash** — the installer and all hooks are bash scripts. Works on macOS and Linux. Windows users should run under WSL.

## Install (human path)

```bash
cd ~/Desktop/fsm-workflow          # or wherever you extracted the package
./install.sh
```

The installer is **idempotent**. Run it as many times as you like — it strips any old registrations pointing into `~/.claude/hooks/` and re-adds fresh ones, so there are no duplicates.

What it does, in order:

1. Verifies `jq` is installed and `~/.claude/` exists.
2. Backs up your existing `~/.claude/settings.json` to `settings.json.bak.<unix-timestamp>`.
3. Copies `agents/`, `hooks/`, `commands/`, and `templates/` into `~/.claude/`.
4. `chmod +x` on every shell script.
5. Merges the four hook registrations into `~/.claude/settings.json` using `jq`. **Your existing hooks, MCP servers, and other settings are preserved.**
6. Validates the final JSON is well-formed. If not, it points you at the backup.

## Install (ask another Claude to do it)

If you'd rather not run shell scripts yourself, open Claude Code in a fresh session and paste the entire contents of `INSTALL_FOR_CLAUDE.md` into the prompt. That file is a ready-to-execute instruction set that walks Claude through the install, with safety checks and validation at every step.

## Using the workflow

After install, in **any** project directory:

```bash
cd ~/your-project
claude                # or `code .` and open the integrated Claude Code panel
```

Once Claude Code is open:

```
/init-workflow
```

This bootstraps the project: it copies `CLAUDE.md`, `.claude/settings.json`, and `.claude/hooks/discipline-gate.sh` into the project. After that, just describe what you want to build. The orchestrator handles the rest:

1. **Brainstorming** — you and the orchestrator talk through the idea. It may invoke `spec-writer` to capture the spec, or `research-scout` to survey prior art.
2. **You say "build it"** — the dispatcher takes over the auto pipeline.
3. **Scouts** read the existing code in parallel (if any).
4. **Architect** synthesizes spec + scout reports into a build manifest.
5. **Task-planner** writes task files and creates `MAP.md` atomically.
6. **Workers** (`fsm-executor` / `fsm-integrator`) execute tasks in dependency waves, in parallel where possible.
7. **Auditors** (`code-auditor`, `bug-scanner`, `dep-checker`) run in parallel on the finished code.
8. **Fix loops** (`code-fixer` for mechanical fixes, `debugger` for complex ones) iterate until clean.
9. **Test-runner** runs the test suite.
10. **Session-closer** resets `MAP.md` and deletes task files when tests pass.

The orchestrator flips status fields in `MAP.md` (PENDING → IN_PROGRESS → DONE) as workers return. Everything else is mechanical.

## Recovery (session resume)

If a session ends mid-build, `MAP.md` is still on disk with the in-progress task state. When you re-open Claude Code in the project, the `surface-map-on-start` hook prints a status summary at session start. The orchestrator sees it, reads `MAP.md` and the affected task files, verifies Registers against the code on disk, regenerates the nonce, and re-dispatches workers with a `RECOVERY:` prefix from the last verified step. Hook-enforced — you don't need to remember to do this.

## Uninstall

```bash
rm -rf ~/.claude/agents/{architect,bug-scanner,code-auditor,code-fixer,code-reviewer,debugger,dep-checker,dispatcher,doc-writer,explore-scout,explore-superscout,file-lister,fsm-executor,fsm-integrator,mock-server,mockup-verifier,research-scout,session-closer,session-handoff,spec-writer,task-planner,test-runner}.md
rm ~/.claude/hooks/{block-map-writes,block-worker-reads,block-model-override,surface-map-on-start}.sh
rm ~/.claude/commands/init-workflow.md
rm -rf ~/.claude/templates
```

Then restore your pre-install `settings.json` from the backup the installer made:

```bash
ls ~/.claude/settings.json.bak.*     # find the most recent
cp ~/.claude/settings.json.bak.<timestamp> ~/.claude/settings.json
```

## Troubleshooting

**"jq: command not found"** — install jq (see Dependencies).

**Hooks don't fire** — confirm they're executable: `ls -la ~/.claude/hooks/`. Every `.sh` file should have the `x` bit set. Re-run `install.sh` if not.

**Agents aren't showing up** — Claude Code loads agents at session start. Close and reopen Claude Code after install.

**`/init-workflow` command not found** — check `ls ~/.claude/commands/init-workflow.md`. If present, close and reopen Claude Code (commands are loaded at startup).

**"Workers can't read CLAUDE.md" errors** — that's the `block-worker-reads` hook doing its job. It's intentional: workers are supposed to read only their task file plus the paths listed under `## Files / Reads` in that file. If a worker genuinely needs CLAUDE.md, the task was planned wrong — update the task, don't disable the hook.

**`MAP.md` got written by the wrong agent** — the `block-map-writes` hook prevents that, but if somehow it fired bypass, restore from the backup the `task-planner` wrote before the bad write. All task writes are atomic against `MAP.md`.

**Coding discipline gate blocks every write** — read the compact XML violation list in the block reason, fix the file, save. The agent should do this automatically. If it's looping, the discipline rule is wrong for your codebase — edit `templates/hooks/discipline-gate.sh` to adjust the checks (but don't install modified versions back over a project that's already initialized).

## Credits

Designed and battle-tested by a fleet operator running a stable of Telegram bots on Google Compute Engine. The discipline SOP + role separation + nonce-proof pattern evolved from watching agents drift, re-reading the same context fifteen times, and writing code that contradicted the spec two hops earlier. The hooks exist because mechanical enforcement beats "please follow the rules" every single time.

## License

MIT — see `LICENSE`.
