---
name: Workflow Phases
description: FSM pipeline lifecycle
color: orange
---

## Workflow phases

### Brainstorming (orchestrator-driven, no auto pipeline)
The orchestrator talks to the user. May invoke `research-scout` for external info or `spec-writer` to capture an idea into `specs/<topic>.md`. No auto-handoff anywhere — the user keeps brainstorming and explicitly signals "build it" when ready.

Session kickoff behavior:
1. User brainstorms in plain conversation.
2. Orchestrator dispatches `research-scout` when external references are needed.
3. Orchestrator dispatches `spec-writer` when intent should be captured into `specs/*.md`.
4. Once the user says "build it", the orchestrator hands the current spec package to `architect` (with scout reports if present), then enters dispatcher-managed pipeline execution.

### Bootstrap (greenfield only)
If no `CLAUDE.md` exists, dispatcher routes to `doc-writer` (pre-workflow mode). doc-writer sets up CLAUDE.md + `.claude/settings.json` + project hooks. Does NOT create MAP.md — `task-planner` does that later.

### Main pipeline (auto, dispatcher-managed)
1. **Scouts** (only if existing code to read) — `explore-scout` / `explore-superscout` in parallel, non-overlapping scopes
2. **Architect** — consumes `specs/*.md` + scout reports + research briefs, produces build manifest
3. **task-planner** — consumes manifest, writes task files + MAP.md (atomic)
4. **Atomizer** — orchestrator runs `python scripts/atomize_task.py <task_files...>` on every multi-step task. Mandatory. Splits into single-step sub-tasks for Haiku-tier execution.
5. **Workers** — `fsm-executor` / `fsm-integrator` in waves (parallel within a wave). Sub-task chains (a→b→c) cascade freely within a wave without interruption. Orchestrator flips PENDING → IN_PROGRESS per worker dispatch.
6. **Wave gate (bug-scanner pair)** — when ALL tasks in a wave reach DONE (worker self-verified), TWO bug-scanners review the wave output in parallel on deterministic shards. APPROVE requires both scanners to approve. REVISE returns the union of flagged task IDs for targeted repair dispatch (max 3 rounds). Flagged tasks route to `code-fixer` for mechanical/simple fixes and `debugger` for complex/logic fixes. After 3 failed rounds → BLOCKED → escalate. **Wave Checkpoint** — If any task in the completed wave carries `requires_user_confirmation: true`, `orchestrate.py` writes `.checkpoint_pending` sentinel and pauses. Next invocation is a no-op until the sentinel is deleted. Options: Approve (continue), Paused (edit session_state.json), or Skip (omit remaining confirmations this session).
7. **Audit** — `audit_discipline.py` + `check_deps.py` run deterministically via subprocess (no LLM calls). `orchestrate.py` gates on the `.audit_clean` sentinel file before proceeding.
8. **Fix loops** — `code-fixer` (discipline + simple bugs) or `debugger` (test failures, complex bugs, broken imports). Max 3 rounds per loop, then ESCALATE.
9. **test-runner** — when all auditors clean
10. **session-closer** — when tests pass. Resets MAP.md, deletes task files.
11. **doc-writer post-workflow** — changelog, deployment notes.

### Wave Gate (bug-scanner pair boundary)

The wave gate runs automatically when all tasks in a wave reach DONE.

1. Workers execute all tasks in a wave (including sub-task chains a→b→c). Each worker self-verifies and sets its task to DONE.
2. Orchestrator marks the completed wave as REVIEW and dispatches two bug-scanner intents for the wave batch (scanner shard 0 and shard 1).
3. **APPROVE** — both scanners return APPROVE. Gate opens and orchestrator advances to wave N+1 (or audit if final wave).
4. **REVISE** — one or both scanners return REVISE. Flagged tasks are computed from the union of scanner guidance, flipped REVIEW → PENDING with REVISE notes in Registers, then re-dispatched to `code-fixer` (simple/mechanical) or `debugger` (complex).
5. **BLOCKED** — after 3 revision rounds on the same wave, the wave enters BLOCKED state. The dispatcher escalates with options: manual fix, merge into integrator task, or accept risk.

One gate cycle per wave boundary. No per-task or per-sub-task gate calls.

### Task Atomization

After `task-planner` produces task files and MAP.md, the orchestrator ALWAYS runs the atomizer script:

```bash
python scripts/atomize_task.py task_801_foo.md task_802_bar.md [...]
```

Atomization is opt-in as of v1.2.3. Only tasks with `atomize: required` in frontmatter are split. The script:

1. Reads each task file, splits multi-step Program sections into single-step sub-tasks.
2. Assigns letter-suffix IDs: `task_801a`, `task_801b`, `task_801c`.
3. Chains sub-task dependencies linearly: `801a` (inherits parent deps) -> `801b` (depends: 801a) -> `801c` (depends: 801b).
4. Rewrites external dependency references: tasks that depended on `task_801` now depend on `task_801c` (the last sub-task).
5. Updates MAP.md: replaces parent entries with sub-task entries.
6. Deletes original parent task files. Single-step tasks pass through unchanged (already atomic).

A multi-step task that cannot be atomized is malformed. Escalate to `task-planner` for rewrite.

**Note:** The atomizer writes MAP.md via Python file I/O (not Claude Code Write/Edit), bypassing the `block-map-writes` hook. This is a documented exception: deterministic transformation, not agent judgment.

### Automated dispatch (`scripts/orchestrate.py`)

`orchestrate.py` is a step-function CLI that automates one orchestration cycle per invocation. Each call reads MAP.md, decides the highest-priority action via a 6-level cascade, dispatches the appropriate agent, and updates state. Exit codes: 0=all done, 1=action taken, 2=waiting, 3=blocked, 4=error, 5=audit_failed.

The orchestrator (this Claude session) runs it in a loop: invoke `PYTHONPATH=. python scripts/orchestrate.py`, inspect exit code, dispatch any pending intents in `.fsm-intents/` as Agent tool calls (`fsm-executor`, `fsm-integrator`, `bug-scanner`, `code-fixer`, `debugger`), write result envelopes, repeat. The script is stateless between invocations — all state lives on disk. Recovery is trivial: re-run from last known state.

Supporting modules in `src/fsm_core/`:
- `action_decider.py` — priority cascade: BLOCKED → REVIEW-wave gate dispatch → WAVE_CHECKPOINT_PENDING → PENDING-ready → ALL_DONE → WAITING
- `map_io.py` / `map_reader.py` — MAP.md status reads + atomic flips under lockfile
- `map_lock.py` — atomic lockfile context manager
- `dispatch_router.py` — claude-session dispatch router
- `claude_session_backend.py` — intent/result transport (`.fsm-intents/`, `.fsm-results/`) plus driver bridge
- `advisor_parser.py` — APPROVE/REVISE verdict parsing + REVISE round counting (shared verdict grammar for bug-scanner outputs)
- `trace.py` — JSONL event logging; `dag_waves.py` — wave computation from dep DAG

### Recovery

On resume the orchestrator reads MAP.md. For IN_PROGRESS tasks: read Registers, verify against disk, regenerate nonce, re-dispatch with `RECOVERY:` prefix from last verified step. For PARTIAL returns, re-dispatch the agent type with `RECOVERY:` — this is progress.
