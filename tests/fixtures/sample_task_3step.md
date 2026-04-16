---
id: task_801
name: sample_feature
state: PENDING
step: 0 of 3
depends: [task_800]
wave: 2
dispatch: fsm-executor
checkpoint: abc123
created: 2026-04-10
atomize: required
---

## Files
Creates:
  src/engine/model_registry.py   # ModelRole enum and resolve_model function
  tests/engine/test_model_registry.py   # Unit tests for resolve_model
Modifies:
  src/config.py   # Add MODEL_ROLES and PHASE_CONFIGS constants
Reads:
  specs/model_tier_spec.md   # Model tier definitions and role assignments

## Program
1. Create `src/engine/model_registry.py` — define `ModelRole` enum and `resolve_model(role)` function that maps each role to its default model tier using MODEL_ROLES from config.
2. Add `MODEL_ROLES` and `PHASE_CONFIGS` constants to `src/config.py` — map each `ModelRole` to a model name string, and define per-phase config dicts referencing those roles.
3. Create `tests/engine/test_model_registry.py` — write unit tests covering `resolve_model` for each `ModelRole`, unknown role error path, and config consistency.

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] `src/engine/model_registry.py` exists with `ModelRole` enum and `resolve_model` function
- [ ] `src/config.py` contains `MODEL_ROLES` and `PHASE_CONFIGS` constants
- [ ] All unit tests in `tests/engine/test_model_registry.py` pass

## Transition Rules
- step DONE → increment step, update Registers
- all steps DONE → state: VERIFY, self-check criteria
- verify pass → state: DONE
- verify fail → state: <failed step>, note failure
