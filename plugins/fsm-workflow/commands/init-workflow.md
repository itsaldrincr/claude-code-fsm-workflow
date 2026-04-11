---
description: Bootstrap the FSM agent workflow in the current directory — installs CLAUDE.md, project hooks, the discipline gate, and orchestrator scripts.
---

The user wants the FSM workflow installed in the current working directory. Execute the bootstrap directly — this is a one-shot setup, no dispatcher needed.

## Prerequisites

This command depends on `~/.claude/templates/` and `~/.claude/scripts/` existing — both are populated by `/fsm-setup-hooks` (which runs `install.sh`). If either is missing, tell the user to run `/fsm-setup-hooks` first and stop.

## Steps

1. **Check whether a workflow already exists.** Run `ls CLAUDE.md .claude/settings.json 2>/dev/null` in the CWD. If both exist, STOP and report "workflow already installed — nothing to do." If only one exists, ask whether to overwrite or merge.

2. **Check prerequisites.** Run `ls ~/.claude/templates/CLAUDE.md ~/.claude/scripts/orchestrate.py 2>&1`. If either is missing, STOP and tell the user to run `/fsm-setup-hooks` first.

3. **Dispatch `doc-writer` in pre-workflow mode** with this exact prompt:

```
Pre-workflow project setup. Target: <current working directory>.

Copy these files verbatim from the user-level templates:
- ~/.claude/templates/CLAUDE.md → <CWD>/CLAUDE.md
- ~/.claude/templates/settings.json → <CWD>/.claude/settings.json
- ~/.claude/templates/hooks/discipline-gate.sh → <CWD>/.claude/hooks/discipline-gate.sh

Then chmod +x the discipline gate.

Do NOT modify the CLAUDE.md template content. If this project has stack-specific commands (e.g., custom test runner), append a small ## Project Notes section at the bottom of CLAUDE.md (max 20 lines). Detect stack from package.json / pyproject.toml.

Do NOT create MAP.md (task-planner does that on first plan). Do NOT create specs/ (spec-writer does that on first invocation).

Report what was created with exact file paths and line counts.
```

4. **Copy orchestrator and audit scripts** from `~/.claude/scripts/` into `<CWD>/scripts/`. Create the directory if it doesn't exist. Copy only if the target doesn't already have them:
   - `~/.claude/scripts/orchestrate.py` → `<CWD>/scripts/orchestrate.py` — automated dispatch loop
   - `~/.claude/scripts/atomize_task.py` → `<CWD>/scripts/atomize_task.py` — mandatory task atomizer
   - `~/.claude/scripts/audit_discipline.py` → `<CWD>/scripts/audit_discipline.py` — AST discipline checker
   - `~/.claude/scripts/check_deps.py` → `<CWD>/scripts/check_deps.py` — import resolution checker
   - `~/.claude/scripts/session_close.py` → `<CWD>/scripts/session_close.py` — test-gated cleanup

5. **Verify the install** after doc-writer returns and scripts are copied:
   - `CLAUDE.md` exists in CWD
   - `.claude/settings.json` exists
   - `.claude/hooks/discipline-gate.sh` exists and is executable
   - `scripts/orchestrate.py`, `scripts/atomize_task.py`, `scripts/audit_discipline.py`, `scripts/check_deps.py`, `scripts/session_close.py` all exist and are executable
   - Report any missing pieces

6. **Confirm to the user:** workflow installed, ready for brainstorming. Suggest next steps: "describe what you want to build, or invoke `spec-writer` to capture an idea. Once you say 'build it', the pipeline auto-dispatches via `python scripts/orchestrate.py`."
