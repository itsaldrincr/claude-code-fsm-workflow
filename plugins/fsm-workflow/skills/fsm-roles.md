---
name: FSM Roles
description: Canonical roles in the FSM pipeline
color: purple
---

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
- `audit_discipline.py` — discipline violations (deterministic AST; replaces `code-auditor` LLM)
- `bug-scanner` — logic bugs (LLM; reasoning-required)
- `check_deps.py` — broken/unused imports (deterministic `importlib`; replaces `dep-checker` LLM)

**Specialists**:
- `code-fixer` — mechanical discipline + simple-bug fixes
- `debugger` — complex bugs, test failures, broken imports, interface drift
- `test-runner` — runs the test suite

**Bookkeepers**:
- `session-closer` — resets MAP.md, deletes task files at end of session
- `doc-writer` — pre-workflow project setup (CLAUDE.md + hooks) and post-workflow updates (changelogs, deploy notes)
- `session-handoff` — writes a self-contained status doc for the next session

## Canonical agent names

The `dispatch` field in task files uses canonical Claude Code subagent type names — `fsm-executor` or `fsm-integrator`, never short forms. The dispatcher copies the value verbatim to the `**Agent:**` line. Short form in a task file = planner bug = ESCALATE.
