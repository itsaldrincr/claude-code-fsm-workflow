# FSM Workflow for Claude Code

**Discipline is enforced by hooks, not personas.** A multi-agent pipeline for Claude Code where 22 subagents operate under strict role separation, context isolation, and nonce-proof reads — so agents can't drift, contradict the spec, or claim work done without proof. Brainstorm → spec → architect → plan → execute → audit → test → close, with mechanical enforcement at every boundary.

## Why this beats persona-based agent packages

Most multi-agent packages give you "Senior Developer", "UI Expert", "QA Engineer" — persona prompts that bias the model's output distribution but do nothing mechanical to stop bad behavior. This package replaces persona with enforcement. At a glance:

- **Hook enforcement, not prompt hints** — workers physically cannot read `MAP.md` / `CLAUDE.md`, cannot write the task tracker, cannot force a weaker model. `permissionDecision: deny` returns from hooks regardless of what the model "wants" to do. Persona is a suggestion; this is a gate.
- **Context isolation by construction** — workers receive exactly one input: an absolute path to their task file. Everything they need is listed inside it. No ambient context, no drift across compactions, no "I remember the spec said..." hallucinations.
- **Single-writer state** — only `task-planner` and `session-closer` may touch `MAP.md`. The orchestrator flips status fields; workers never write shared state. This kills the entire class of "helpful" cross-writes that corrupt trackers in loose multi-agent setups.
- **Nonce-proof reads** — every task file carries a `checkpoint` hex string. Workers must echo the current nonce in their Registers update. Forgot to read the file? Can't produce the nonce. Task not done. Challenge-response, not vibes.
- **Stateless workers** — every turn re-reads from disk. Session resume, context compaction, and mid-task recovery are all trivially correct: there is no "memory" to lose.
- **Explicit FSM with verifiable transitions** — tasks have states (`PENDING` → `IN_PROGRESS` → `VERIFY` → `DONE`), acceptance criteria that check against disk, and a session that won't close until audit and tests are both clean.
- **Parallel waves with dependency cascade** — workers run concurrently within a wave. The orchestrator flips status as tasks return and auto-dispatches the next wave when dependencies resolve.
- **Coding discipline is a PostToolUse gate** — every `.py` / `.ts` write runs a discipline check. Violations return as a compact XML block the agent treats like a compiler error: read, fix, retry in-loop.
- **One-command install** — drop 22 agents, 4 hooks, 1 slash command, and project templates into `~/.claude/` with `./install.sh`. Idempotent; re-runnable; backs up your existing settings before touching anything.

**Where it isn't better**: this is built for multi-file builds with verification loops. For one-shot questions, quick scripts, or creative brainstorming, a single persona agent is simpler and the FSM overhead is absurd. Use the right tool for the task.

## How this compares to other Claude Code multi-agent packages

Based on a 2026-04-08 survey of four competing packages (stars as of survey date). Every competitor ships "disciplined" or "orchestrated" in their marketing copy; this table reflects what they actually enforce mechanically versus what they describe in prompts.

| Property | **This package** | `wshobson/agents`<br/>(33k★) | `gsd-build/get-shit-done`<br/>(49k★) | `oh-my-claudecode`<br/>(25k★) | `disler/hooks-observability`<br/>(1.3k★) |
|---|:---:|:---:|:---:|:---:|:---:|
| Write-authority enforcement (blocks unauthorized agents from writing shared state) | ✅ hook returns `deny` | ❌ | ⚠️ `O_EXCL` lock (prevents races, not unauth writes) | ❌ | ❌ |
| Context isolation (workers physically cannot read `MAP.md` / `CLAUDE.md`) | ✅ hook returns `deny` | ❌ | ❌ | ❌ | ❌ |
| Nonce-proof reads (worker must echo checkpoint hex to complete a task) | ✅ | ❌ | ❌ | ❌ | ❌ |
| `PostToolUse` discipline gate on code (blocks non-compliant `.py` / `.ts` writes) | ✅ XML violation block | ❌ | ❌ (only validates commit msg) | ❌ | ❌ |
| Stateless workers with single-input contract (re-read from disk every turn) | ✅ | ❌ prompt stacking | ⚠️ fresh context per agent | ❌ | N/A |
| Hook-enforced role separation | ✅ | ❌ prompt only | ❌ prompt only | ❌ prompt only | N/A |
| Agent count / breadth | 22 | **182** | 24 | 19 | 2 |
| Plugin marketplace / skills system | ❌ | **✅ 75 plugins, 147 skills** | ⚠️ partial | ⚠️ 11+ skills | ❌ |
| Multi-runtime support (Codex, Gemini, etc.) | ❌ | ❌ | **✅ 13+ runtimes at install time** | ⚠️ via tmux | ❌ |
| Observability / live tracing | ❌ | ❌ | ❌ | ⚠️ hook observers | **✅ Vue dashboard + WebSocket + SQLite** |
| Published benchmarks | ❌ | **✅ PluginEval 3-layer framework** | ❌ | ⚠️ SWE-bench harness (no results) | ❌ |

**Reading the table**: the top six rows are about enforcement — whether the package physically prevents an agent from doing the wrong thing. This package is the only one that returns `permissionDecision: deny` from hooks on anything more substantial than `rm -rf`. Every competitor relies on prompt instructions and trusts the agent to follow them.

The bottom five rows are about breadth, ecosystem, and instrumentation — where other packages genuinely beat this one. `wshobson/agents` wins on agent breadth and has a real evaluation system. `gsd-build` wins on runtime DAG analysis and multi-runtime support. `disler` is the only package with serious observability. If your priority is "a huge catalog of domain experts" or "a live dashboard of what my agents are doing," those packages serve different needs than this one does.

**Pick this package when**: you need disciplined multi-file builds with verification loops and you have been burned by agents drifting, hallucinating, writing to the wrong files, or claiming work done without proof. **Pick a different package when**: you want domain breadth, a marketplace, heterogeneous LLM orchestration, or a live visual dashboard — those are all things the packages above do better, and they can often be layered on top of this one without conflict.

## What this is

Claude Code already supports subagents. This package wires 22 of them together into a disciplined pipeline with strict role separation (orchestrator, dispatcher, scouts, architect, planner, workers, auditors, fixers, test-runner, bookkeepers), hook-level enforcement of context isolation and write authority, and a brainstorming → build → audit → test → close lifecycle that runs autonomously once you've said "build it."

Read `templates/CLAUDE.md` for the full SOP. It's the source of truth for how the workflow runs; the agents and hooks are just the mechanical enforcement of what's written there.

## What's in this package

```
fsm-workflow/
├── README.md                                   # this file
├── LICENSE                                     # MIT
├── install.sh                                  # idempotent full installer (Mode 1)
├── INSTALL_FOR_CLAUDE.md                       # paste-ready prompt for another Claude (Mode 3)
├── .claude-plugin/
│   └── marketplace.json                        # Claude Code plugin marketplace manifest
├── hooks/                                      # user-level hooks → ~/.claude/hooks/ (installed by install.sh only)
│   ├── block-map-writes.sh                     # only task-planner + session-closer may touch MAP.md
│   ├── block-worker-reads.sh                   # workers can't read MAP.md / CLAUDE.md (enforces context isolation)
│   ├── block-model-override.sh                 # stops callers from forcing a weaker model on an agent
│   └── surface-map-on-start.sh                 # SessionStart: MAP.md status summary for recovery awareness
└── plugins/
    └── fsm-workflow/                           # the marketplace plugin (Mode 2 entry point)
        ├── .claude-plugin/
        │   └── plugin.json                     # plugin metadata
        ├── agents/                             # 22 subagent definitions → ~/.claude/agents/
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
        ├── commands/
        │   ├── init-workflow.md                # /init-workflow — bootstrap a project
        │   └── fsm-setup-hooks.md              # /fsm-setup-hooks — complete Mode 2 install
        └── templates/                          # project scaffold → ~/.claude/templates/
            ├── CLAUDE.md                       # full workflow SOP
            ├── settings.json                   # project-level settings with discipline gate registered
            └── hooks/
                └── discipline-gate.sh          # PostToolUse hook: blocks .py/.ts writes with violations
```

## Dependencies

- **Claude Code** installed and working. https://docs.claude.com/en/docs/claude-code
- **jq** — the installer uses it to merge hook registrations into your existing `settings.json` without clobbering it.
  - macOS: `brew install jq`
  - Linux: `sudo apt install jq` (or your distro's equivalent)
- **bash** — the installer and all hooks are bash scripts. Works on macOS and Linux. Windows users should run under WSL.

## Install — two modes

There are two ways to install this package, and they are **not equivalent**. Pick carefully.

### Mode 1: Full install (recommended — includes the enforcement hooks)

```bash
git clone https://github.com/itsaldrincr/claude-code-fsm-workflow.git
cd claude-code-fsm-workflow
./install.sh
```

This installs:

- 22 agents → `~/.claude/agents/`
- 4 user-level hooks → `~/.claude/hooks/` **← this is the moat of the package**
- 2 slash commands (`/init-workflow`, `/fsm-setup-hooks`) → `~/.claude/commands/`
- Project templates (`CLAUDE.md`, discipline gate) → `~/.claude/templates/`
- Hook registrations merged idempotently into `~/.claude/settings.json`

**This is the install you want.** The hooks are what make this package different from every other Claude Code agent collection. Without them, you have 22 agents with no enforcement.

The installer is idempotent — safe to re-run. It backs up your existing `settings.json` before any change.

### Mode 2: Claude Code plugin marketplace (agents only — hooks must be added in a second step)

```
/plugin marketplace add itsaldrincr/claude-code-fsm-workflow
/plugin install fsm-workflow
/fsm-setup-hooks
```

The Claude Code plugin marketplace format does not currently support installing user-level hooks. If you install via `/plugin install fsm-workflow`, you get the agents, commands, and templates — but **the hooks will not be registered**, which means:

- Workers can read `MAP.md` and `CLAUDE.md` (no context isolation)
- Any agent can write `MAP.md` (no single-writer authority)
- The discipline gate will not fire on `.py` / `.ts` writes
- The workflow loses its entire enforcement story

**You must run `/fsm-setup-hooks` immediately after `/plugin install fsm-workflow`** to complete the install. That command walks you through cloning the repo and running `./install.sh` — or offers to do it for you. It is not optional if you want the package as described.

**Why this two-step exists**: the Claude Code plugin marketplace ships agents, commands, skills, and templates, but does not (as of today) have a mechanism for registering user-level hook scripts in `~/.claude/settings.json`. Every other package in the marketplace is persona-based and doesn't need hooks to function. This one does. Until the marketplace format grows hook support, Mode 2 requires the manual follow-up.

### Mode 3: Ask another Claude to do it

Open a fresh Claude Code session and paste the entire contents of `INSTALL_FOR_CLAUDE.md` into the prompt. That file is a ready-to-execute instruction set that walks Claude through the full install (Mode 1 equivalent) with safety checks and validation at every step.

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
rm ~/.claude/commands/init-workflow.md ~/.claude/commands/fsm-setup-hooks.md
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

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md) for version history. Format follows [Keep a Changelog](https://keepachangelog.com/), versioning follows [SemVer](https://semver.org/). Check the `[Unreleased]` section at the top to see what has landed on `main` since the last tagged release.

## License

MIT — see `LICENSE`.
