---
name: Task File Format
description: Self-contained FSM task file structure
color: blue
requires_user_confirmation: bool = false
---

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
requires_user_confirmation: bool = false  # whether wave-checkpoint review is needed before proceeding
atomize: required | optional | skip = optional  # task-planner automation hint
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

**Task Atomization Hint** — the optional `atomize:` field guides `task-planner` and the atomizer script:
- `required` — Force atomization. Set this for multi-step tasks with ≥5 Creates, ≥4 steps, or a step exceeding ~40 worker-visible tokens.
- `optional` (default) — Atomize if task-planner heuristics suggest it (backwards compatible with v1.2.2 tasks).
- `skip` — Never atomize, even if the task appears large. Use when steps are sequential and cannot logically split.

The atomizer script (`scripts/atomize_task.py`) respects `atomize: required` by splitting multi-step tasks into single-step sub-tasks with letter suffixes (801a, 801b, 801c) and chaining dependencies. The atomizer's MAP.md write (atomic transformation, not LLM judgment) remains a documented exception to the `block-map-writes` hook.

## Valid Task States

| State | Meaning |
|---|---|
| PENDING | Not yet dispatched |
| IN_PROGRESS | Dispatched to a worker |
| EXECUTING | Worker is actively running steps |
| VERIFY | Worker self-checking acceptance criteria |
| DONE | Worker completed and self-verified. Wave-level bug-scanner pair approval required before next wave starts. |
| REVIEW | Wave under bug-scanner pair review at wave boundary |
| BLOCKED | Max bug-scanner revisions (3) reached; requires manual intervention |
| FAILED | Worker failed; see Registers for reason |
| PARTIAL | Worker hit context limit mid-task; re-dispatch from last step |

**REVIEW** — entered at the wave level when all tasks in a wave are DONE and the bug-scanner pair is reviewing the wave output. Individual tasks remain DONE during wave review; the REVIEW state applies to the wave gate.

**BLOCKED** — entered when the bug-scanner pair has returned REVISE 3 times on a wave and targeted tasks still fail review. The orchestrator surfaces an escalation to the user. BLOCKED is terminal until manual intervention.

## Checkpoint Nonce — Proof of Read

Every task file carries a `checkpoint` field — a 6-char hex string from `openssl rand -hex 3`. When an agent updates Registers, it must include the current nonce. After writing, it generates a new nonce. This is challenge-response: if the agent can't produce the current nonce, it didn't read the file.
