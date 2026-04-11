---
id: bench_{instance_id}
name: swe_bench_{instance_id}
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-integrator
# NOTE: requires_user_confirmation is intentionally omitted.
# Benchmark runs must be fully autonomous end-to-end without user prompts.
# The default is False; we rely on that rather than explicitly setting it.
---

## Files
Creates:
  — depends on instance —
Modifies:
  — depends on instance —
Reads:
  — depends on instance —

## Program
1. Execute orchestrate.py against this SWE-bench instance workspace end-to-end.

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] orchestrate.py completes and produces a patch file
- [ ] Patch is saved to bench_result.json under this workspace
- [ ] Exit code is recorded

## Transition Rules
- step DONE → increment step, update Registers
- all steps DONE → state: VERIFY, self-check criteria
- verify pass → state: DONE
- verify fail → state: <failed step>, note failure
