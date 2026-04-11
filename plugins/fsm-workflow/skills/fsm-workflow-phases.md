---
name: Workflow Phases
description: FSM pipeline lifecycle
color: orange
---

## Workflow phases

### Brainstorming (orchestrator-driven, no auto pipeline)
The orchestrator talks to the user. May invoke `research-scout` for external info or `spec-writer` to capture an idea into `specs/<topic>.md`. No auto-handoff anywhere — the user keeps brainstorming and explicitly signals "build it" when ready.

### Bootstrap (greenfield only)
If no `CLAUDE.md` exists, dispatcher routes to `doc-writer` (pre-workflow mode). doc-writer sets up CLAUDE.md + `.claude/settings.json` + project hooks. Does NOT create MAP.md — `task-planner` does that later.

### Main pipeline (auto, dispatcher-managed)
1. **Scouts** (only if existing code to read) — `explore-scout` / `explore-superscout` in parallel, non-overlapping scopes
2. **Architect** — consumes `specs/*.md` + scout reports + research briefs, produces build manifest
3. **task-planner** — consumes manifest, writes task files + MAP.md (atomic)
4. **Atomizer** — orchestrator runs `python scripts/atomize_task.py <task_files...>` on every multi-step task. Mandatory. Splits into single-step sub-tasks for Haiku-tier execution.
5. **Workers** — `fsm-executor` / `fsm-integrator` in waves (parallel within a wave). Sub-task chains (a→b→c) cascade freely within a wave without interruption. Orchestrator flips PENDING → IN_PROGRESS per worker dispatch.
6. **Wave gate (advisor)** — when ALL tasks in a wave reach DONE (worker self-verified), ONE advisor (Opus) reviews the entire wave output. The advisor reads all files created/modified across all wave tasks. APPROVE → gate opens, wave N+1 starts. REVISE → targeted tasks re-dispatched, wave re-reviewed (max 3 rounds). After 3 failed rounds → BLOCKED → escalate. **Wave Checkpoint** — If any task in the completed wave carries `requires_user_confirmation: true`, `orchestrate.py` writes `.checkpoint_pending` sentinel and pauses. Next invocation is a no-op until the sentinel is deleted. Options: Approve (continue), Paused (edit session_state.json), or Skip (omit remaining confirmations this session).
7. **Audit** — `audit_discipline.py` + `check_deps.py` run deterministically via subprocess (no LLM calls); `bug-scanner` LLM runs in parallel for logic checks. `orchestrate.py` gates on the `.audit_clean` sentinel file before proceeding.
8. **Fix loops** — `code-fixer` (discipline + simple bugs) or `debugger` (test failures, complex bugs, broken imports). Max 3 rounds per loop, then ESCALATE.
9. **test-runner** — when all auditors clean
10. **session-closer** — when tests pass. Resets MAP.md, deletes task files.
11. **doc-writer post-workflow** — changelog, deployment notes.

### Advisor Loop (per-wave gate)

The advisor gates wave transitions, not individual task completions. Workers cascade freely within a wave — the advisor reviews the batch at the wave boundary.

1. Workers execute all tasks in a wave (including sub-task chains a→b→c). Each worker self-verifies and sets its task to DONE.
2. When ALL tasks in the wave reach DONE, `orchestrate.py` detects wave completion and dispatches ONE advisor (Opus) to review the entire wave output.
3. Advisor reads all files created/modified across all wave tasks. Evaluates acceptance criteria and coding discipline for each task.
4. **APPROVE** — advisor confirms the wave output meets all criteria. Gate opens. Orchestrator advances to wave N+1 (or audit if final wave).
5. **REVISE** — advisor identifies specific tasks with issues and returns corrective guidance per task. Those tasks are re-dispatched to their original worker type with `REVISE:` prefix. Unaffected tasks remain DONE. After targeted fixes, the wave is re-reviewed.
6. **BLOCKED** — after 3 revision rounds on the same wave, the wave enters BLOCKED state. The dispatcher escalates with options: manual fix, merge into integrator task, or skip advisor (accept risk).

One advisor call per wave boundary. No per-task or per-sub-task advisor calls.

### Task Atomization

After `task-planner` produces task files and MAP.md, the orchestrator ALWAYS runs the atomizer script:

```bash
python scripts/atomize_task.py task_801_foo.md task_802_bar.md [...]
```

Atomization is mandatory, not optional. The script:

1. Reads each task file, splits multi-step Program sections into single-step sub-tasks.
2. Assigns letter-suffix IDs: `task_801a`, `task_801b`, `task_801c`.
3. Chains sub-task dependencies linearly: `801a` (inherits parent deps) -> `801b` (depends: 801a) -> `801c` (depends: 801b).
4. Rewrites external dependency references: tasks that depended on `task_801` now depend on `task_801c` (the last sub-task).
5. Updates MAP.md: replaces parent entries with sub-task entries.
6. Deletes original parent task files. Single-step tasks pass through unchanged (already atomic).

A multi-step task that cannot be atomized is malformed. Escalate to `task-planner` for rewrite.

**Note:** The atomizer writes MAP.md via Python file I/O (not Claude Code Write/Edit), bypassing the `block-map-writes` hook. This is a documented exception: deterministic transformation, not agent judgment.

### Automated dispatch (`scripts/orchestrate.py`)

`orchestrate.py` is a step-function CLI that automates one orchestration cycle per invocation. Each call reads MAP.md, decides the highest-priority action via a 6-level cascade, dispatches the appropriate agent, and updates state. Exit codes: 0=all done, 1=action taken, 2=waiting, 3=blocked, 4=error.

The orchestrator runs it in a loop. The script is stateless between invocations — all state lives on disk. Recovery is trivial: re-run from last known state.

**Streaming visibility (preferred).** When a build phase begins, the orchestrator invokes Claude Code's Monitor tool with `bash scripts/orchestrate_monitor.sh` as a persistent driver. The script loops `orchestrate.py` and emits state-count events (`[HH:MM:SS] PENDING=N REVIEW=N DONE=N`) on stdout as MAP.md changes — each line becomes a conversation event without bloating the orchestrator's context with per-worker transcripts. Fall back to plain `bash scripts/orchestrate.py` loops if Monitor is unavailable.

Supporting modules in `src/fsm_core/`:
- `action_decider.py` — priority cascade: BLOCKED → REVIEW → PENDING-ready → ALL_DONE → WAITING → ERROR
- `map_io.py` / `map_reader.py` — MAP.md status reads + atomic flips under lockfile
- `map_lock.py` — atomic lockfile context manager
- `subprocess_dispatch.py` — worker / advisor / REVISE dispatch via `claude` CLI subprocesses
- `advisor_parser.py` — APPROVE/REVISE verdict parsing + REVISE round counting
- `trace.py` — JSONL event logging; `dag_waves.py` — wave computation from dep DAG

### Recovery

On resume the orchestrator reads MAP.md. For IN_PROGRESS tasks: read Registers, verify against disk, regenerate nonce, re-dispatch with `RECOVERY:` prefix from last verified step. For PARTIAL returns, re-dispatch the agent type with `RECOVERY:` — this is progress.
