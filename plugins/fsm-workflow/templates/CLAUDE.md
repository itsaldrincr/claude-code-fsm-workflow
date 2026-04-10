# Coding Discipline SOP

These rules apply to ALL code generated in this workspace. They are non-negotiable. If a rule conflicts with a specific instruction, follow the specific instruction and note the deviation.

## Functions

**Max 2 parameters.** If a function needs more, the parameters describe an object. Create a Pydantic BaseModel (Python) or interface (TypeScript) and pass that.

**Functions do one thing.** If you can't describe what a function does without "and", split it.

**Name functions as verbs.** `get_user`, `validate_schema`, `compile_prompt`.

**Return early on failure.** Check error conditions at the top and return/raise immediately. The happy path reads straight down.

**Max 20 lines per function body.** Extract sub-operations into private helpers.

## Classes and Objects

**Objects carry state. Functions transform it.** No state → it's a function or module of functions, not a class with static methods.

**Max 3 public methods per class.** Constructors don't count. Exception: data classes (many fields, no behaviour).

**Compose, don't inherit.** Pass objects as dependencies; don't extend base classes.

**Schema-first data structures.** Every object crossing a function boundary is a Pydantic model (Python) or interface/Zod schema (TypeScript). Validate data from external sources (API, disk, user input) before processing.

## Naming

- **Variables describe what they hold.** `user_id`, `cache_ttl`. Single letters only in comprehensions and loop indices.
- **Booleans read as questions.** `is_loaded`, `has_errors`, `should_retry`.
- **Constants are UPPER_SNAKE_CASE.** No magic numbers (except 0 and 1) — every number gets a named constant.
- **Files are snake_case.** One module per file.

## Error Handling

**Never swallow exceptions silently.** Every `except` block logs, re-raises, or returns a meaningful error state.

**Use typed error returns for expected failures.** Result objects with status fields. Reserve exceptions for unexpected failures.

**Retry with backoff, not with hope.** Max 3 retries, exponential backoff, log every attempt.

## Architecture

**Single responsibility per module.** Each file does one thing.

**Dependencies flow one direction.** Higher layers depend on lower layers, never the reverse. Circular imports = wrong architecture.

**Configuration lives in one place.** No hardcoded values in module code.

**Interfaces are contracts.** Clearly defined input/output types (Pydantic in Python, interfaces in TypeScript).

## Code Structure

**Imports at the top, three groups:** stdlib → third-party → local. One blank line between groups.

**No dead code.** Not called → delete it. Version control remembers.

**Docstrings on public functions only.** One line: what the function does.

**Type hints on everything.** Every parameter, return type, class field.

## What NOT to Do

Never generate code that:
- Has functions with more than 2 parameters
- Has classes with more than 3 public methods
- Contains magic numbers or hardcoded paths
- Swallows exceptions silently
- Uses inheritance where composition works
- Has circular imports
- Contains commented-out code
- Lacks type hints on public interfaces
- Uses `print()` instead of `logging`
- Puts configuration values in module code

---

# Task Coordination SOP

This workspace runs a multi-agent pipeline. Roles never overlap.

## Roles

**Orchestrator (the main conversation)** — talks to the user, owns brainstorming, dispatches subagents, flips MAP.md status fields as agents return reports. Never writes code itself.

**Dispatcher** — coordinator subagent that reads pipeline state and produces dispatch instructions (which agent runs next, with what prompt). Read-only on MAP.md. Never runs agents.

**Brainstorming tools** (orchestrator-invoked, not in auto pipeline):
- `research-scout` — external research (libraries, patterns, prior art)
- `spec-writer` — captures intent into `specs/<topic>.md` files

**Planner**:
- `task-planner` — consumes the architect's manifest, writes task files + creates/updates MAP.md

**Synthesizer**:
- `architect` — consumes spec files + scout reports + research briefs, produces a build manifest

**Scouts** (read-only):
- `explore-scout` / `explore-superscout` — read code/docs, return structured reports
- `research-scout` — external web research

**Workers** (write code):
- `fsm-executor` — single-module tasks (1–4 files in one directory)
- `fsm-integrator` — cross-module tasks (3+ directories, factory wiring, test updates)

**Reviewer** (post-execution, pre-audit):
- `advisor` — post-execution reviewer; returns APPROVE or REVISE verdict (Opus-tier)

**Auditors** (parallel, post-execution):
- `code-auditor` — discipline violations
- `bug-scanner` — logic bugs
- `dep-checker` — broken imports

**Specialists**:
- `code-fixer` — mechanical discipline + simple-bug fixes
- `debugger` — complex bugs, test failures, broken imports, interface drift
- `test-runner` — runs the test suite

**Bookkeepers**:
- `session-closer` — resets MAP.md, deletes task files at end of session
- `doc-writer` — pre-workflow project setup (CLAUDE.md + hooks) and post-workflow updates (changelogs, deploy notes)
- `session-handoff` — writes a self-contained status doc for the next session

## MAP.md write authority — TWO subagents only

| Agent | What it writes |
|---|---|
| `task-planner` | Creates MAP.md (greenfield) and updates it during planning. Atomic with task files. |
| `session-closer` | Resets MAP.md to the clean template at end of session. |
| Orchestrator (main conversation) | Flips status fields (PENDING → IN_PROGRESS → DONE) as agents return reports. |
| Everyone else | **Strictly forbidden.** Enforced by the `block-map-writes` hook. |

## Worker context isolation

Workers receive **only one thing** as input: their task file path. The dispatcher's worker-prompt template is exact:

```
Execute task file: <absolute/path/to/task_NNN_name.md>

This task file is self-contained. Read it, follow its Protocol, write code per its Program steps, update Registers with nonce proof, set state to DONE on success.
```

Workers do not read MAP.md, CLAUDE.md, specs, or any other project context. The task file's `## Files` section lists every path the worker needs. Enforced by the `block-worker-reads` hook.

## Canonical agent names

The `dispatch` field in task files uses canonical Claude Code subagent type names — `fsm-executor` or `fsm-integrator`, never short forms. The dispatcher copies the value verbatim to the `**Agent:**` line. Short form in a task file = planner bug = ESCALATE.

## Task File Format

Task files live at the workspace root and are self-contained process control blocks.

```markdown
---
id: task_NNN
name: short_snake_name
state: PENDING
step: 0 of N
depends: [task IDs]
wave: N
dispatch: fsm-executor | fsm-integrator
checkpoint: XXXXXX
created: YYYY-MM-DD
---

## Files
Creates:
  path/new.ts                # one-line purpose
  tests/path/new.test.ts
Modifies:
  path/existing.ts           # what changes
Reads:
  path/interface.ts          # why
  #docs/specs/section.md     # why

## Program
1. Step — specific, references exact files/functions
2. Step — ...
3. Step — max 3 per task

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] Verifiable against code on disk
- [ ] All functions comply with coding discipline
- [ ] All tests pass

## Transition Rules
- step DONE → increment step, update Registers
- all steps DONE → state: VERIFY, self-check criteria
- verify pass → state: DONE
- verify fail → state: <failed step>, note failure
```

### Valid Task States

| State | Meaning |
|---|---|
| PENDING | Not yet dispatched |
| IN_PROGRESS | Dispatched to a worker |
| EXECUTING | Worker is actively running steps |
| VERIFY | Worker self-checking acceptance criteria |
| DONE | Worker completed and self-verified. Wave-level advisor approval required before next wave starts. |
| REVIEW | Wave under advisor review at wave boundary |
| BLOCKED | Max advisor revisions (3) reached; requires manual intervention |
| FAILED | Worker failed; see Registers for reason |
| PARTIAL | Worker hit context limit mid-task; re-dispatch from last step |

**REVIEW** — entered at the wave level when all tasks in a wave are DONE and the advisor is reviewing the wave output. Individual tasks remain DONE during wave review; the REVIEW state applies to the wave gate.

**BLOCKED** — entered when the advisor has returned REVISE 3 times on a wave and targeted tasks still fail review. The orchestrator surfaces an escalation to the user. BLOCKED is terminal until manual intervention.

### Checkpoint Nonce — Proof of Read

Every task file carries a `checkpoint` field — a 6-char hex string from `openssl rand -hex 3`. When an agent updates Registers, it must include the current nonce. After writing, it generates a new nonce. This is challenge-response: if the agent can't produce the current nonce, it didn't read the file.

## MAP.md Format

```markdown
# MAP

## Active Tasks

### Wave 1 (parallel — no dependencies)
Project/
  src/engine/      [task_801_model_registry.md] ........ PENDING
  src/types/       [task_802_message_types.md] ......... PENDING

### Wave 2 (depends on Wave 1)
Project/
  src/composites/  [task_803_tier_rewrite.md] .......... PENDING  depends: 801, 802

## Completed (awaiting audit)
— none —

## File Directory

### task_801 → src/engine/ + src/config.ts
Creates:
  src/engine/model-registry.ts      # ModelRole, resolveModel(role)
  tests/engine/model-registry.test.ts
Modifies:
  src/config.ts                     # MODEL_ROLES, PHASE_CONFIGS
Reads:
  src/config.ts                     # current structure
  #docs/specs/v4_spec.md            # model roster
```

The File Directory mirrors each task file's `## Files` section. Both are mandatory and must match.

## Hook enforcement

This workflow is enforced mechanically, not just by instruction.

**User-level (`~/.claude/settings.json`):**
- `block-map-writes` — PreToolUse on Write/Edit. Blocks MAP.md writes from any agent except `task-planner`, `session-closer`, or the orchestrator.
- `block-worker-reads` — PreToolUse on Read. Blocks worker subagents from reading MAP.md or CLAUDE.md.
- `surface-map-on-start` — SessionStart. If MAP.md exists in CWD, emits a status summary so the orchestrator notices recovery situations.

**Pipeline-enforce hooks (`~/.claude/hooks/pipeline-enforce/`):**
- `validate-map-transition` — PreToolUse on Edit targeting MAP.md. Blocks invalid state transitions (e.g. PENDING→DONE). Uses `VALID_TRANSITIONS` dict. Emits deny with specific reason.
- `nudge-orchestrate` — PostToolUse on Read of MAP.md. If PENDING or REVIEW tasks exist and `scripts/orchestrate.py` is in CWD, emits a nudge message reminding the orchestrator to use the automated dispatch loop.

**Project-level (`.claude/settings.json`):**
- `discipline-gate` — PostToolUse on Write/Edit for `.py`/`.ts` files. Returns `decision: "block"` with violations if discipline is violated. Treat the block reason as a compiler error: read it, fix the file, retry. Do NOT stop and wait for user input.

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
6. **Wave gate (advisor)** — when ALL tasks in a wave reach DONE (worker self-verified), ONE advisor (Opus) reviews the entire wave output. The advisor reads all files created/modified across all wave tasks. APPROVE → gate opens, wave N+1 starts. REVISE → targeted tasks re-dispatched, wave re-reviewed (max 3 rounds). After 3 failed rounds → BLOCKED → escalate. Wave N+1 starts only after the wave-level advisor approves.
7. **Audit** — `code-auditor` + `bug-scanner` + `dep-checker` in parallel
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

The orchestrator runs it in a loop. The script is stateless between invocations — all state lives on disk (MAP.md + task files). Recovery is trivial: re-run from last known state.

Supporting modules in `src/fsm_core/`:
- `action_decider.py` — pure function priority cascade: BLOCKED → REVIEW → PENDING-ready → ALL_DONE → WAITING → ERROR
- `map_io.py` — atomic MAP.md status flips under lockfile
- `map_reader.py` — combines MAP.md statuses with task file frontmatter
- `subprocess_dispatch.py` — dispatches workers, advisor, and REVISE rounds via `claude` CLI
- `advisor_parser.py` — parses APPROVE/REVISE verdicts, counts revision rounds
- `map_lock.py` — atomic lockfile context manager
- `dag_waves.py` — DAG wave computation
- `trace.py` — JSONL event logging

### Recovery
On session resume the orchestrator reads MAP.md (the SessionStart hook surfaces it). For IN_PROGRESS tasks: read the task file's Registers, verify against disk, regenerate the nonce, re-dispatch with `RECOVERY:` prefix from the last verified step.

For PARTIAL returns (worker hit a context limit mid-task): re-dispatch the same agent type with `RECOVERY:` — no round counter, this is progress.

## Default behaviour

This workflow runs underneath every request. The user just asks for what they want. The pipeline runs:

1. **Any request comes in** → Orchestrator reads MAP.md first. Active tasks → recovery mode. Clean → fresh start.
2. **Brainstorming** happens in conversation, with `spec-writer` and `research-scout` invoked on demand.
3. **User signals "build it"** → dispatcher takes over auto pipeline.
4. **Workers run autonomously** in waves. Orchestrator monitors completions and cascades dependent tasks.
5. **Audit runs automatically** when all tasks DONE.
6. **Session closes automatically** when tests pass.

## Rules

- **Workers are stateless.** Always read from disk. Never rely on conversation memory.
- **Every edit covered by a task.** No ad-hoc changes.
- **Read before write — always.** The nonce proves it. Hooks enforce it.
- **Write after act — always.** Registers update after every step.
- **Only `task-planner` and `session-closer` write MAP.md.** The orchestrator flips status fields. Hook-enforced.
- **Workers never read MAP.md or CLAUDE.md.** Their task file is self-contained. Hook-enforced.
- **Canonical agent names everywhere.** `fsm-executor`, not `executor`.
- **Coding discipline gate is not optional.** Block reason = compiler error. Fix and retry.
- **Advisor gates wave transitions, not individual tasks.** Workers cascade freely within a wave. ONE advisor reviews the full wave output at the boundary. Wave N+1 starts only after wave-level APPROVE.
- **Use `scripts/orchestrate.py` for dispatch.** The automated dispatch loop reads state, decides action, dispatches agents, and updates MAP.md. Don't manually flip statuses or dispatch workers when orchestrate.py can do it.
- **When in doubt, read the map.** Cheaper to re-read than guess wrong.

## Model Tier Defaults (Max Account)

No cost difference on Max. Tier choice is quality, speed, and rate limit pressure.

| Role | Default Model | Rationale |
|---|---|---|
| task-planner | opus | Highest-stakes planning. Free on Max. |
| architect | opus | Manifest quality determines build quality. |
| advisor | opus | Must judge code quality at expert level. |
| fsm-integrator | sonnet | Cross-module wiring with explicit specs. Opus escalation via dispatcher override. |
| fsm-executor | haiku (via dispatcher `**Model:**` override) | All executor tasks are atomized single-step. Speed + 529 headroom. |
| debugger | sonnet | Reasoning about failures. Opus escalation for complex bugs. |
| dispatcher | sonnet | Decision routing, not deep reasoning. |
| code-fixer | haiku | Mechanical fixes from auditor reports. |
| explore-scout | haiku | Fast file reads, structured reports. |
| explore-superscout | sonnet | Dense document reasoning. |

---

