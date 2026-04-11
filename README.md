# FSM Workflow for Claude Code

**Discipline enforced by hooks. Dispatch automated by code. Audits run as scripts, not agents.** A multi-agent pipeline for Claude Code where 23 subagents operate under strict role separation, context isolation, and nonce-proof reads — with an automated dispatch engine that reads state, decides actions, dispatches workers, gates waves through Opus-tier review, and audits the output via deterministic AST checks. Brainstorm → spec → architect → plan → atomize → execute → advisor gate → audit (scripts) → test → close.

## What's new in v1.2.2

- **Opt-in PHASE CHECKPOINT.** New per-task frontmatter flag `requires_user_confirmation: bool = false`. When set, `orchestrate.py` halts at the end of the containing wave via a `.checkpoint_pending` sentinel; the orchestrator agent fires Claude Code's `AskUserQuestion` and deletes the sentinel on approval. Default pipeline stays fully autonomous — pipelines with zero flagged tasks are byte-identical to v1.1.2.
- **SWE-bench Verified harness skeleton (`bench/`).** Scripts for isolating instances, driving `orchestrate.py` end-to-end, capturing the produced patch via git diff, evaluating against expected diffs with a local heuristic backend, and emitting per-instance + aggregate result JSON. No baseline numbers shipped — infrastructure only. First third-party deps in the repo, scoped strictly to `bench/requirements.txt`.
- **Progressive-disclosure skills.** Downstream `plugins/fsm-workflow/templates/CLAUDE.md` slimmed from 399 → 134 lines by carving six passively-loaded Claude Code skills (`fsm-roles`, `fsm-task-format`, `fsm-map-format`, `fsm-workflow-phases`, `fsm-hook-enforcement`, `model-tier-routing`). Installer copies skills to `~/.claude/skills/` idempotently. `init-workflow` self-installs the skills if missing.
- **Parallel worker dispatch.** `dispatch_workers_parallel` in `src/fsm_core/subprocess_dispatch.py` uses `ThreadPoolExecutor(max_workers=8)` to dispatch ready tasks concurrently via subprocess. Serial chains (a→b→c) still cascade sequentially — parallel where possible, sequential where dependent.
- **Wave-batch advisor.** `src/fsm_core/action_decider.py` gates advisor dispatch on whole-wave REVIEW completion. One advisor call reviews the full wave at once. On REVISE, an explicit `FAILING TASKS: task_NNNa, ...` line in the advisor response re-dispatches only the flagged tasks, not the whole wave.
- **Worker prompt hardening.** `_build_worker_prompt` now mandates real tool calls (no hallucinating DONE via text), pre-DONE verification, acceptance checkbox flipping, nonce proof in Registers, and REVISE awareness via Registers re-read.
- **`--permission-mode bypassPermissions`** added to `claude -p` worker subprocess invocations. Fixes a silent failure mode where the Write tool was blocked by default on fresh paths.
- **Post-build critical fixes:** `_revise_wave_batch` no longer short-circuits on first BLOCKED (deadlock fix); `_DECISION_CASCADE` moves `_find_wave_checkpoint` ahead of `_check_ready_wave` (gate-bypass fix); `SessionState._parse_state_file` now round-trips `checkpoints_skipped_this_session`; `_run_cycle` re-checks the checkpoint sentinel post-decide to shrink the write-race window.
- **458 tests** across `fsm_core`, `bench/`, `orchestrate`, install, and split-helper suites.

## What's new in v1.1.2

- **Model-tier drift fix.** `fsm-executor` was shipping with `model: sonnet` and `fsm-integrator` with `model: opus` since v1.1.0, despite the Model Tier Defaults table (below) calling for `haiku` and `sonnet` respectively. Both agent frontmatters are now corrected. Marketplace and direct-clone installs pick up the new defaults automatically; re-run `install.sh` (or re-install the plugin) to apply.
- **CHANGELOG footer links** for `[1.1.1]` and `[Unreleased]` were never added during the v1.1.1 bump. Restored alongside the new `[1.1.2]` entry.

## What's new in v1.1.1

- **Deterministic audit scripts replace 2 of the 3 LLM auditors** — `scripts/audit_discipline.py` (AST-based coding discipline checker, replaces `code-auditor`) and `scripts/check_deps.py` (import resolution + unused-import checker, replaces `dep-checker`). Each runs in ~1 second against the full codebase with zero token cost. Exit 0 clean / 1 violations / 2 error. Output: `file:line:scope -- rule -- detail`, sorted by (file, line) for determinism. `bug-scanner` stays as an LLM subagent because logic-bug detection still needs reasoning.
- **`scripts/session_close.py`** — test-gated session cleanup. Runs pytest; on pass, deletes `task_*.md`, deletes `.audit_clean` sentinel, resets MAP.md to clean template. On failure, no cleanup.
- **Post-ALL_DONE audit gate in `scripts/orchestrate.py`** — subprocess calls to audit scripts with `PYTHONPATH` propagation, 600s timeouts, `stderr` capture, dry-run short-circuit, lockfile-guarded `.audit_clean` sentinel to prevent concurrent-orchestrator races. New `EXIT_AUDIT_FAILED = 5` and `AuditGateResult` dataclass. Failing `session_close.py` now maps to `EXIT_ERROR` instead of silently returning success.
- **Installer fixes (critical)** — `install.sh` now actually installs the 4 top-level enforcement hooks (`block-map-writes.sh`, `block-worker-reads.sh`, `block-model-override.sh`, `surface-map-on-start.sh`). These shipped in `hooks/` since v0.1.0 but were never copied or registered — fresh marketplace users got zero moat despite the docs. Also fixed: missing `src/repo_map/` source tree, missing `hooks/post_tool_trace.sh`, broken agent path after the v1.1.0 plugin restructure.
- **Version drift repaired** — `plugin.json` and `marketplace.json` were stuck at `0.1.1` through v1.0.0 and v1.1.0. Both now match the tag scheme at `1.1.1`.
- **Atomizer bug fix** — `scripts/atomize_task.py` now correctly rewrites cross-parent dependencies during multi-task atomization. Previously, atomizing `task_804` with `depends: [task_801, task_802, task_803]` left subtask files pointing to deleted parent IDs instead of each parent's last subtask (`task_801c`, `task_802c`, `task_803c`).
- **101 new tests** across `test_audit_discipline.py`, `test_check_deps.py`, `test_session_close.py`, plus new `TestAuditGate*` classes in `test_orchestrate.py`. Full suite: 315 tests.

## What's new in v1.1.0

- **Pipeline automation engine** — `scripts/orchestrate.py` is a stateless step-function that reads MAP.md, decides the highest-priority action, dispatches workers/advisor, and updates state. Run it in a loop; it does one thing per invocation. Exit codes: 0=all done, 1=action taken, 2=waiting, 3=blocked, 4=error.
- **Task atomizer** — `scripts/atomize_task.py` splits multi-step tasks into single-step sub-tasks for Haiku-tier execution. Mandatory after planning. Rollback on failure.
- **Per-wave advisor gate** — workers cascade freely within a wave (a→b→c chains complete without interruption). ONE Opus advisor reviews the entire wave output at the boundary. APPROVE opens the gate to wave N+1. REVISE targets specific tasks (max 3 rounds, then BLOCKED).
- **Pipeline-enforce hooks** — `validate_map_transition.py` blocks invalid state transitions (e.g. PENDING→DONE). `nudge_orchestrate.py` reminds the orchestrator to use the automated dispatch loop.
- **`src/fsm_core/` — 10 Python modules** — action decider, advisor parser, subprocess dispatch, MAP.md I/O, lockfile, DAG waves, frontmatter parser, session state, trace logger.
- **315 tests** covering all modules.

## Why this beats persona-based agent packages

Most multi-agent packages give you "Senior Developer", "UI Expert", "QA Engineer" — persona prompts that bias the model's output distribution but do nothing mechanical to stop bad behavior. This package replaces persona with enforcement:

- **Hook enforcement, not prompt hints** — workers physically cannot read `MAP.md` / `CLAUDE.md`, cannot write the task tracker, cannot force a weaker model. `permissionDecision: deny` from hooks.
- **Context isolation by construction** — workers receive exactly one input: a task file path. No ambient context, no drift.
- **Single-writer state** — only `task-planner` and `session-closer` may touch `MAP.md`. Invalid transitions are blocked by `validate_map_transition.py`.
- **Nonce-proof reads** — every task file carries a `checkpoint` hex string. Workers must echo the current nonce. Challenge-response, not vibes.
- **Automated dispatch** — `orchestrate.py` reads state from disk, decides what to do, dispatches the right agent at the right model tier, and updates MAP.md. Stateless between invocations.
- **Per-wave advisor gate** — Opus reviews all wave output before the next wave starts. Not per-task (too slow), not skippable (too risky).
- **Mandatory atomization** — every multi-step task is split into single-step sub-tasks. Haiku executes them fast; the advisor reviews the batch.
- **Coding discipline is a PostToolUse gate** — every `.py` / `.ts` write runs a discipline check. Violations return as a compiler error.
- **One-command install** — `./install.sh` drops agents, hooks, scripts, and templates into `~/.claude/`. Idempotent.

**Where it isn't better**: for one-shot questions, quick scripts, or creative brainstorming, a single agent is simpler and the FSM overhead is absurd.

## How this compares to other packages

| Property | **This package** | `wshobson/agents` | `gsd-build/get-shit-done` | `oh-my-claudecode` | `disler/hooks-observability` |
|---|:---:|:---:|:---:|:---:|:---:|
| Hook-enforced write authority | **yes** | no | partial | no | no |
| Hook-enforced context isolation | **yes** | no | no | no | no |
| Nonce-proof reads | **yes** | no | no | no | no |
| Discipline gate on code writes | **yes** | no | no | no | no |
| Automated dispatch engine | **yes** | no | no | no | no |
| Per-wave advisor gate | **yes** | no | no | no | no |
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
├── hooks/                              # user-level enforcement hooks
│   ├── block-map-writes.sh             # only task-planner + session-closer may write MAP.md
│   ├── block-worker-reads.sh           # workers can't read MAP.md / CLAUDE.md
│   ├── block-model-override.sh         # stops callers from forcing weaker models
│   ├── surface-map-on-start.sh         # SessionStart: MAP.md status summary for recovery
│   ├── validate_map_transition.py      # blocks invalid state transitions (e.g. PENDING→DONE)
│   ├── nudge_orchestrate.py            # nudges toward scripts/orchestrate.py when tasks exist
│   └── post_tool_trace.sh              # JSONL event trace of every tool call for FSM runs
├── src/fsm_core/                       # pipeline automation modules (Python, stdlib only)
│   ├── action_decider.py               # 6-level priority cascade
│   ├── advisor_parser.py               # APPROVE/REVISE verdict parsing
│   ├── subprocess_dispatch.py          # worker/advisor/revise dispatch via claude CLI
│   ├── map_io.py                       # atomic MAP.md status flips under lockfile
│   ├── map_reader.py                   # MAP.md + task file frontmatter reader
│   ├── map_lock.py                     # atomic lockfile with stale-lock reclaim
│   ├── dag_waves.py                    # DAG wave computation + cycle detection
│   ├── frontmatter.py                  # task file YAML frontmatter parser
│   ├── session_state.py                # session state JSON projection
│   └── trace.py                        # JSONL event trace appender
├── src/repo_map/                       # repo-map indexing (Python + JS)
│   ├── indexer.py / indexer_js.py      # AST symbol + import extraction
│   ├── models.py                       # FileIndex, Symbol, IndexRequest dataclasses
│   ├── store.py                        # persistent index storage
│   └── hooks/                          # PreToolUse/PostToolUse/SessionStart hooks for fresh indexes
├── scripts/                            # CLI tools
│   ├── orchestrate.py                  # automated dispatch loop (one action per invocation)
│   ├── atomize_task.py                 # splits multi-step tasks into single-step sub-tasks
│   ├── audit_discipline.py             # AST discipline checker — replaces code-auditor LLM
│   ├── check_deps.py                   # import resolution + unused-import checker — replaces dep-checker LLM
│   └── session_close.py                # test-gated cleanup — replaces session-closer LLM
├── tests/                              # 315 tests (stdlib only, no deps)
├── plugins/fsm-workflow/               # Claude Code plugin marketplace structure
│   ├── agents/                         # 23 subagent definitions
│   ├── commands/                       # /init-workflow, /fsm-setup-hooks
│   └── templates/                      # CLAUDE.md, settings.json, discipline-gate.sh
├── CHANGELOG.md
├── LICENSE                             # MIT
└── README.md
```

## Dependencies

- **Claude Code** — https://docs.claude.com/en/docs/claude-code
- **jq** — `brew install jq` (macOS) or `sudo apt install jq` (Linux)
- **Python 3.11+** — for `src/fsm_core/`, `scripts/`, and pipeline-enforce hooks. Stdlib only, no pip install.
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
- **`src/fsm_core/` + `src/repo_map/`** Python trees → `~/.claude/hooks/fsm-trace/fsm_core/` and `~/.claude/hooks/repo-map/src/repo_map/`
- **2 slash commands** (`/init-workflow`, `/fsm-setup-hooks`) → `~/.claude/commands/` (via plugin install) or available directly after running this installer
- **13 hook registrations** merged into `~/.claude/settings.json` with the correct event + matcher pairs (`PreToolUse` Write/Edit/MultiEdit, Read, Agent, Edit for validate; `PostToolUse` Read, Grep, Edit/Write/MultiEdit, unscoped for trace; `SessionStart` × 2; `Stop`)

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

This bootstraps `CLAUDE.md`, `.claude/settings.json`, and the discipline gate. Then describe what you want to build.

### The pipeline

1. **Brainstorm** — talk through the idea. `spec-writer` captures intent, `research-scout` surveys prior art.
2. **"Build it"** — dispatcher takes over.
3. **Scouts** read existing code in parallel.
4. **Architect** produces a build manifest from specs + scout reports.
5. **Task-planner** writes task files + MAP.md.
6. **Atomizer** splits multi-step tasks into single-step sub-tasks (`python scripts/atomize_task.py`).
7. **Workers** execute in dependency waves. `fsm-executor` (Haiku) for atomized tasks, `fsm-integrator` (Sonnet) for cross-module work.
8. **Advisor gate** — when all wave tasks are DONE, one Opus advisor reviews the batch. APPROVE → next wave. REVISE → targeted re-dispatch (max 3 rounds).
9. **Audit** — `audit_discipline.py` + `check_deps.py` run deterministically via subprocess (~1s each, zero token cost). `bug-scanner` LLM runs in parallel for logic-bug detection. `orchestrate.py` gates on the `.audit_clean` sentinel file before proceeding.
10. **Fix loops** — `code-fixer` or `debugger` iterate until clean.
11. **Test-runner** — full suite.
12. **Session-closer** — `session_close.py` runs pytest, gates all cleanup on exit 0, then deletes `task_*.md`, removes the sentinel, and resets `MAP.md` to the clean template.

### Automated dispatch

```bash
python scripts/orchestrate.py --workspace .
```

Reads MAP.md, decides the next action, dispatches one agent, updates state, exits. Run in a loop for full automation. `--dry-run` to preview without executing.

## Recovery

If a session ends mid-build, MAP.md persists with in-progress state. On restart, `surface-map-on-start` prints status. The orchestrator reads task Registers, verifies against disk, regenerates nonces, and re-dispatches with `RECOVERY:` prefix.

## Model tiers (Max account)

No cost difference on Max. Tier choice is quality vs. speed vs. rate-limit pressure.

| Role | Model | Rationale |
|---|---|---|
| task-planner, architect, advisor | opus | Highest-stakes planning and review |
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

# Slash commands + templates
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

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md). Format: [Keep a Changelog](https://keepachangelog.com/). Versioning: [SemVer](https://semver.org/).

## License

MIT — see `LICENSE`.
