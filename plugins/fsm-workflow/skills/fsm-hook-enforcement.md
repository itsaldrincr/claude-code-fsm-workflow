---
name: Hook Enforcement
description: Mechanical enforcement of FSM workflow rules
color: red
---

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
