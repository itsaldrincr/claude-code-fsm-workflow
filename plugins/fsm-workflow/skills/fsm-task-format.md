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

## Valid Task States

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

## Checkpoint Nonce — Proof of Read

Every task file carries a `checkpoint` field — a 6-char hex string from `openssl rand -hex 3`. When an agent updates Registers, it must include the current nonce. After writing, it generates a new nonce. This is challenge-response: if the agent can't produce the current nonce, it didn't read the file.
