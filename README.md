# FSM Workflow for Claude Code

**Discipline enforced by hooks. Dispatch automated by code. Audits run as scripts, not agents.** A multi-agent pipeline for Claude Code where 23 subagents operate under strict role separation, context isolation, and nonce-proof reads — with an automated dispatch engine that reads state, decides actions, dispatches workers, gates waves through paired bug-scanner review, and audits the output via deterministic AST checks. Brainstorm → spec → architect → plan → atomize → execute → bug-scanner pair gate → audit (scripts) → test → close.

## What's new in v1.2.6

- **Stdlib-only runtime.** The FSM pipeline (orchestrate.py, fsm_core, audit scripts, hooks) now runs on Python stdlib alone. No SDK, no HTTP client, no `pip install` required. `requirements.txt` is a placeholder kept for install parity.
- **Claude session is the driver.** The main Claude session (this conversation) loops `orchestrate.py`, reads pending intents from `.fsm-intents/`, dispatches Agent tool calls (`fsm-executor`, `fsm-integrator`, `bug-scanner`, `code-fixer`, `debugger`), writes result envelopes, repeats. No external daemon, no async event loop.
- **`orchestrate_monitor.sh` + `--daemon` flag removed.** The monitor script was written for an out-of-process SDK driver that no longer exists — the Claude session cannot be driven from a looping shell script.
- **Slim template regeneration.** `plugins/fsm-workflow/templates/CLAUDE.md` is now deterministically produced from the canonical `CLAUDE.md` via `scripts/split_claude_md.py`. The full workflow text lives in six skill files under `plugins/fsm-workflow/skills/`.

### Carried forward from v1.2.5

- **Bug-scanner pair wave gate.** Two Sonnet bug-scanners review wave output in parallel on deterministic file shards. Unanimous APPROVE required to open the gate. REVISE routes flagged tasks to `code-fixer` (simple/mechanical) or `debugger` (complex/logic).
- **Claude-session intent/result transport.** Workers and scanners dispatch via `.fsm-intents/` + `.fsm-results/` through `claude_session_backend.py`.
- **Three-gate wave pipeline.** (1) `wave_deterministic_gate.evaluate_wave` runs audit + deps + pytest deterministically, (2) `advisor_cache.lookup_verdict` checks content-hash cache, (3) two `bug-scanner` agents on disjoint shards.
- **Opt-in atomization.** `atomize: required` frontmatter field controls which tasks get split. Default `optional` preserves backwards compatibility.
- **`src/config.py` + `src/fsm_core/` modules.** Central constants, verdict caching, auto-heal, dispatch routing, orchestrate lock, startup checks, wave deterministic gate, worker heartbeat.
- **`/init-workflow` copies full `src/` tree.** `src/config.py` + `src/fsm_core/` + `requirements.txt` into every initialized project. `orchestrate.py` no longer fails with `ModuleNotFoundError` on fresh installs.

## Why this beats persona-based agent packages

Most multi-agent packages give you "Senior Developer", "UI Expert", "QA Engineer" — persona prompts that bias the model's output distribution but do nothing mechanical to stop bad behavior. This package replaces persona with enforcement:

- **Hook enforcement, not prompt hints** — workers physically cannot read `MAP.md` / `CLAUDE.md`, cannot write the task tracker, cannot force a weaker model. `permissionDecision: deny` from hooks.
- **Context isolation by construction** — workers receive exactly one input: a task file path. No ambient context, no drift.
- **Single-writer state** — only `task-planner` and `session-closer` may touch `MAP.md`. Invalid transitions are blocked by `validate_map_transition.py`.
- **Nonce-proof reads** — every task file carries a `checkpoint` hex string. Workers must echo the current nonce. Challenge-response, not vibes.
- **Automated dispatch** — `orchestrate.py` reads state from disk, decides what to do, dispatches the right agent at the right model tier, and updates MAP.md. Stateless between invocations.
- **Bug-scanner pair wave gate** — two Sonnet scanners review all wave output on deterministic shards before the next wave starts. Both must approve. Not per-task (too slow), not skippable (too risky).
- **Opt-in atomization** — tasks flagged `atomize: required` are split into single-step sub-tasks. Haiku executes them fast; the scanners review the batch.
- **Coding discipline is a PostToolUse gate** — every `.py` / `.ts` write runs a discipline check. Violations return as a compiler error.
- **One-command install** — `./install.sh` drops agents, hooks, scripts, templates, and `src/fsm_core/` into `~/.claude/`. Idempotent.

**Where it isn't better**: for one-shot questions, quick scripts, or creative brainstorming, a single agent is simpler and the FSM overhead is absurd.

## How this compares to other packages

| Property | **This package** | `wshobson/agents` | `gsd-build/get-shit-done` | `oh-my-claudecode` | `disler/hooks-observability` |
|---|:---:|:---:|:---:|:---:|:---:|
| Hook-enforced write authority | **yes** | no | partial | no | no |
| Hook-enforced context isolation | **yes** | no | no | no | no |
| Nonce-proof reads | **yes** | no | no | no | no |
| Discipline gate on code writes | **yes** | no | no | no | no |
| Automated dispatch engine | **yes** | no | no | no | no |
| Bug-scanner pair wave gate | **yes** | no | no | no | no |
| State transition validation hook | **yes** | no | no | no | no |
| Agent count / breadth | 23 | **182** | 24 | 19 | 2 |
| Deterministic audit scripts (not LLM) | **yes** | no | no | no | no |
| Plugin marketplace / skills | no | **yes** | partial | partial | no |
| Multi-runtime support | no | no | **yes** | partial | no |
| Live observability dashboard | no | no | no | partial | **yes** |

## What's in this package

```
fsm-workflow/
├── install.sh                          # idempotent full installer (13 hooks + agents + fsm_core)
├── requirements.txt                    # placeholder — FSM pipeline is stdlib-only
├── conftest.py                         # root pytest config
├── hooks/                              # user-level enforcement hooks
│   ├── block-map-writes.sh             # only task-planner + session-closer may write MAP.md
│   ├── block-worker-reads.sh           # workers can't read MAP.md / CLAUDE.md
│   ├── block-model-override.sh         # stops callers from forcing weaker models
│   ├── surface-map-on-start.sh         # SessionStart: MAP.md status summary for recovery
│   ├── validate_map_transition.py      # blocks invalid state transitions (e.g. PENDING→DONE)
│   ├── nudge_orchestrate.py            # nudges toward scripts/orchestrate.py when tasks exist
│   └── post_tool_trace.sh              # JSONL event trace of every tool call for FSM runs
├── src/
│   ├── config.py                       # central constants (dispatch mode, model map, timeouts)
│   └── fsm_core/                       # pipeline automation modules
│       ├── action_decider.py           # 6-level priority cascade
│       ├── advisor_cache.py            # content-hash verdict cache for bug-scanner APPROVE
│       ├── advisor_parser.py           # APPROVE/REVISE verdict parsing (bug-scanner grammar)
│       ├── auto_heal.py               # startup stale-task healer (IN_PROGRESS → PENDING)
│       ├── claude_session_backend.py   # intent/result transport for dispatch
│       ├── dag_waves.py               # DAG wave computation + cycle detection
│       ├── dispatch_contract.py        # dispatch dataclasses
│       ├── dispatch_router.py          # claude-session dispatch router
│       ├── frontmatter.py             # task file YAML frontmatter parser
│       ├── map_io.py                  # atomic MAP.md status flips under lockfile
│       ├── map_lock.py                # atomic lockfile with stale-lock reclaim
│       ├── map_reader.py              # MAP.md + task file frontmatter reader
│       ├── orchestrate_lock.py        # orchestrate-level lockfile
│       ├── session_state.py           # session state JSON projection
│       ├── startup_checks.py          # MAP/task state drift warnings
│       ├── trace.py                   # JSONL event trace appender
│       ├── wave_deterministic_gate.py # deterministic pre-gate (audit + deps + pytest)
│       └── worker_heartbeat.py        # atomic heartbeat writer for liveness
├── src/repo_map/                       # repo-map indexing (Python + JS)
│   ├── indexer.py / indexer_js.py      # AST symbol + import extraction
│   ├── models.py                       # FileIndex, Symbol, IndexRequest dataclasses
│   ├── store.py                        # persistent index storage
│   └── hooks/                          # PreToolUse/PostToolUse/SessionStart hooks
├── scripts/                            # CLI tools
│   ├── orchestrate.py                  # step-function dispatch (one cycle per invocation)
│   ├── claude_session_driver.py        # intent/result driver bridge
│   ├── atomize_task.py                 # splits multi-step tasks into single-step sub-tasks
│   ├── audit_discipline.py             # AST discipline checker — replaces code-auditor LLM
│   ├── check_deps.py                   # import resolution checker — replaces dep-checker LLM
│   ├── session_close.py                # test-gated cleanup
│   └── split_claude_md.py              # CLAUDE.md → slim template + 6 skills
├── tests/                              # 590+ tests (pytest)
├── plugins/fsm-workflow/               # Claude Code plugin marketplace structure
│   ├── agents/                         # 23 subagent definitions
│   ├── commands/                       # /init-workflow, /fsm-setup-hooks
│   ├── skills/                         # 6 on-demand skill files
│   └── templates/                      # CLAUDE.md, settings.json, discipline-gate.sh
├── CHANGELOG.md
├── LICENSE                             # MIT
└── README.md
```

## Dependencies

- **Claude Code** — https://docs.claude.com/en/docs/claude-code
- **jq** — `brew install jq` (macOS) or `sudo apt install jq` (Linux)
- **Python 3.11+** (stdlib only) — for `src/fsm_core/`, `scripts/`, and pipeline-enforce hooks
- **bash** — installer and shell hooks

## Install

### Mode 1: Full install (recommended)

```bash
git clone https://github.com/itsaldrincr/claude-code-fsm-workflow.git
cd claude-code-fsm-workflow
./install.sh
```

This installs:
- **23 agents** → `~/.claude/agents/`
- **13 hook files across 4 categories** → `~/.claude/hooks/`
  - 4 top-level enforcement hooks: `block-map-writes.sh`, `block-worker-reads.sh`, `block-model-override.sh`, `surface-map-on-start.sh`
  - 2 pipeline-enforce hooks: `pipeline-enforce/validate_map_transition.py`, `pipeline-enforce/nudge_orchestrate.py`
  - 6 repo-map hooks: `repo-map/src/repo_map/hooks/{pre_read,post_read,post_grep,post_edit,session_start,stop}.py`
  - 1 FSM trace hook: `fsm-trace/post_tool_trace.sh`
- **`src/` Python package** → `~/.claude/src/` (config.py + 19 fsm_core modules)
- **6 scripts** → `~/.claude/scripts/`
- **6 skills** → `~/.claude/skills/`
- **2 slash commands** (`/init-workflow`, `/fsm-setup-hooks`) → `~/.claude/commands/`
- **Templates** → `~/.claude/templates/`
- **13 hook registrations** merged into `~/.claude/settings.json`

Idempotent. Backs up `settings.json` before any change (`settings.json.bak.<timestamp>`). Re-running adds zero entries if the install is already complete.

### Mode 2: Plugin marketplace (agents only — hooks added separately)

```
/plugin marketplace add itsaldrincr/claude-code-fsm-workflow
/plugin install fsm-workflow
/fsm-setup-hooks
```

The marketplace does not support hook registration. **You must run `/fsm-setup-hooks`** after install to get enforcement. Without it, you have agents with no teeth.

### Mode 3: Ask Claude

Paste `INSTALL_FOR_CLAUDE.md` into a fresh Claude Code session.

## Usage

After install, in any project directory:

```bash
claude
/init-workflow
```

This bootstraps `CLAUDE.md`, `.claude/settings.json`, the discipline gate, `scripts/` (orchestrator + audit tools), `src/` (fsm_core modules), and `requirements.txt`. Then describe what you want to build.

### The pipeline

1. **Brainstorm** — talk through the idea. `spec-writer` captures intent, `research-scout` surveys prior art.
2. **"Build it"** — dispatcher takes over.
3. **Scouts** read existing code in parallel.
4. **Architect** produces a build manifest from specs + scout reports.
5. **Task-planner** writes task files + MAP.md.
6. **Atomizer** splits flagged tasks into single-step sub-tasks (`python scripts/atomize_task.py`).
7. **Workers** execute in dependency waves. `fsm-executor` (Haiku) for atomized tasks, `fsm-integrator` (Sonnet) for cross-module work.
8. **Bug-scanner pair gate** — when all wave tasks are DONE, two Sonnet bug-scanners review the batch on deterministic shards. Both must APPROVE to open the gate. REVISE → targeted re-dispatch to `code-fixer` or `debugger` (max 3 rounds).
9. **Audit** — `audit_discipline.py` + `check_deps.py` run deterministically via subprocess (~1s each, zero token cost). `bug-scanner` LLM runs in parallel for logic-bug detection. `orchestrate.py` gates on the `.audit_clean` sentinel file before proceeding.
10. **Fix loops** — `code-fixer` or `debugger` iterate until clean.
11. **Test-runner** — full suite.
12. **Session-closer** — `session_close.py` runs pytest, gates all cleanup on exit 0, then deletes `task_*.md`, removes the sentinel, and resets `MAP.md` to the clean template.

### Automated dispatch

```bash
# One cycle per invocation. Orchestrator (the Claude session) loops it.
PYTHONPATH=. python scripts/orchestrate.py --workspace .

# Preview without executing
PYTHONPATH=. python scripts/orchestrate.py --workspace . --dry-run
```

Reads MAP.md, decides the next action, enqueues worker/scanner intents to `.fsm-intents/`, exits with a status code. The Claude session picks up pending intents and dispatches them as Agent tool calls, writes result envelopes to `.fsm-results/`, then re-runs orchestrate.py to apply them. Stateless between invocations — all state lives on disk.

## Recovery

If a session ends mid-build, MAP.md persists with in-progress state. On restart, `surface-map-on-start` prints status. The orchestrator reads task Registers, verifies against disk, regenerates nonces, and re-dispatches with `RECOVERY:` prefix. `auto_heal.py` automatically flips stale IN_PROGRESS tasks back to PENDING on heartbeat timeout.

## Model tiers (Max account)

No cost difference on Max. Tier choice is quality vs. speed vs. rate-limit pressure.

| Role | Model | Rationale |
|---|---|---|
| task-planner, architect | opus | Highest-stakes planning |
| bug-scanner (x2) | sonnet | Paired wave-boundary reviewers; unanimous APPROVE required |
| fsm-integrator, debugger | sonnet | Cross-module reasoning |
| dispatcher | sonnet | Decision routing |
| fsm-executor, code-fixer, explore-scout | haiku | Speed + rate-limit headroom for atomized single-step tasks |

## Uninstall

```bash
# 23 agent definitions
rm -rf ~/.claude/agents/{advisor,architect,bug-scanner,code-auditor,code-fixer,code-reviewer,debugger,dep-checker,dispatcher,doc-writer,explore-scout,explore-superscout,file-lister,fsm-executor,fsm-integrator,mock-server,mockup-verifier,research-scout,session-closer,session-handoff,spec-writer,task-planner,test-runner}.md

# 4 top-level enforcement hooks
rm ~/.claude/hooks/{block-map-writes,block-worker-reads,block-model-override,surface-map-on-start}.sh

# Pipeline-enforce + fsm-trace + repo-map hook trees
rm -rf ~/.claude/hooks/pipeline-enforce
rm -rf ~/.claude/hooks/fsm-trace
rm -rf ~/.claude/hooks/repo-map

# src/, scripts, skills, commands, templates
rm -rf ~/.claude/src
rm -rf ~/.claude/scripts
rm -rf ~/.claude/skills
rm ~/.claude/commands/init-workflow.md ~/.claude/commands/fsm-setup-hooks.md
rm -rf ~/.claude/templates
```

Restore your pre-install settings: `cp ~/.claude/settings.json.bak.<timestamp> ~/.claude/settings.json` (pick the oldest backup from before the install to revert all 13 hook registrations at once).

## Troubleshooting

**"jq: command not found"** — install jq (see Dependencies).

**Hooks don't fire** — confirm they're executable: `ls -la ~/.claude/hooks/`. Re-run `install.sh`.

**Agents aren't showing up** — close and reopen Claude Code after install.

**"Workers can't read CLAUDE.md"** — that's `block-worker-reads` doing its job. Workers read only their task file. If a worker needs CLAUDE.md, the task was planned wrong.

**`MAP.md` transition denied** — `validate_map_transition.py` blocked an invalid state flip. Check the deny reason for the valid transitions from the current state.

**Discipline gate blocks every write** — read the violation list in the block reason, fix the file. The agent should do this automatically.

**`ModuleNotFoundError: No module named 'src'`** — `orchestrate.py` requires the `src/` package. Re-run `/init-workflow` or copy `src/` from `~/.claude/src/` to your project root. Also make sure you invoke it with `PYTHONPATH=. python scripts/orchestrate.py` (the project root must be on `sys.path`).

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md). Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/).

## License

MIT — see `LICENSE`.
