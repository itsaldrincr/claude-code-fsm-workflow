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

## Task Coordination

This workspace runs a multi-agent FSM pipeline. Roles never overlap.

## MAP.md write authority

| Agent | Writes |
|---|---|
| `task-planner` | Creates/updates MAP.md (atomic with task files) |
| `session-closer` | Resets MAP.md at end of session |
| Orchestrator | Flips status fields (PENDING → IN_PROGRESS → DONE) |
| Everyone else | **Forbidden.** Enforced by `block-map-writes` hook. |

## Worker context isolation

Workers receive **only one thing**: their task file path. The worker-prompt is exact: `Execute task file: <path>. This task file is self-contained. Read it, follow its Protocol, write code per its Program steps, update Registers with nonce proof, set state to DONE on success.` Workers do not read MAP.md, CLAUDE.md, specs, or any other project context. The task file's `## Files` section lists every path needed. Enforced by the `block-worker-reads` hook.

## Default Behaviour

1. Any request → Orchestrator reads MAP.md first. Active tasks → recovery mode. Clean → fresh start.
2. Brainstorming in conversation with `spec-writer` and `research-scout` on demand.
3. User signals "build it" → dispatcher takes over auto pipeline.
4. Workers run autonomously in waves. Orchestrator monitors completions and cascades dependent tasks.
5. Audit runs automatically when all tasks DONE.
6. Session closes automatically when tests pass.

## Rules

- **Workers are stateless.** Always read from disk. Never rely on conversation memory.
- **Every edit covered by a task.** No ad-hoc changes.
- **Read before write — always.** The nonce proves it. Hooks enforce it.
- **Write after act — always.** Registers update after every step.
- **Only `task-planner` and `session-closer` write MAP.md.** The orchestrator flips status fields. Hook-enforced.
- **Workers never read MAP.md or CLAUDE.md.** Their task file is self-contained. Hook-enforced.
- **Advisor gates wave transitions, not individual tasks.** Workers cascade freely within a wave. ONE advisor reviews full wave output at boundary.
- **Use `scripts/orchestrate.py` for dispatch.** The automated dispatch loop reads state, decides action, dispatches agents, and updates MAP.md.

## Project Notes

This project builds features destined for installation into `~/.claude/` — custom hooks, skills, agent definitions, and harness extensions.

- **Source of truth** lives in this repo. `~/.claude/` holds installed copies (build artifacts). Edit here, then re-install.
- **Stack**: shell + python. No formal package manager. Python scripts use stdlib only unless a feature requires a library.
- **Testing**: `python -m pytest tests/ -q` runs 427 tests covering fsm_core, orchestrate.py, atomize_task.py, hooks, repo-map, audit, check_deps, session_close.
- **Install**: `bash install.sh` copies hooks and scripts to `~/.claude/`, registers hook entries. Idempotent.

---

## Related Skills

- [fsm-roles](/skills/fsm-roles.md) — Agent roles and canonical names
- [fsm-task-format](/skills/fsm-task-format.md) — Task file structure, states, nonce
- [fsm-map-format](/skills/fsm-map-format.md) — MAP.md structure and file directory
- [fsm-workflow-phases](/skills/fsm-workflow-phases.md) — Pipeline phases and wave gate
- [fsm-hook-enforcement](/skills/fsm-hook-enforcement.md) — Hook system
- [model-tier-routing](/skills/model-tier-routing.md) — Model tier assignments
