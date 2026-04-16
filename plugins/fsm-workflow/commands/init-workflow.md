---
description: Bootstrap the FSM agent workflow in the current directory — installs CLAUDE.md, project hooks, the discipline gate, and orchestrator scripts.
---

The user wants the FSM workflow installed in the current working directory. Execute the bootstrap directly — this is a one-shot setup, no dispatcher needed.

## Prerequisites

This command depends on `~/.claude/templates/`, `~/.claude/scripts/`, and `~/.claude/skills/` existing — all are populated by `/fsm-setup-hooks` (which runs `install.sh`). The `~/.claude/skills/` directory should contain:
  - `fsm-roles.md`
  - `fsm-task-format.md`
  - `fsm-map-format.md`
  - `fsm-hook-enforcement.md`
  - `model-tier-routing.md`
  - `fsm-workflow-phases.md`

If any are missing, tell the user to run `/fsm-setup-hooks` first and stop.

## Steps

1. **Check whether a workflow already exists.** Run `ls CLAUDE.md .claude/settings.json 2>/dev/null` in the CWD. If both exist, STOP and report "workflow already installed — nothing to do." If only one exists, ask whether to overwrite or merge.

2. **Check prerequisites.** Run `ls ~/.claude/templates/CLAUDE.md ~/.claude/scripts/orchestrate.py ~/.claude/skills/fsm-roles.md ~/.claude/skills/fsm-task-format.md ~/.claude/skills/fsm-map-format.md ~/.claude/skills/fsm-hook-enforcement.md ~/.claude/skills/model-tier-routing.md ~/.claude/skills/fsm-workflow-phases.md 2>&1`. If any are missing, STOP and tell the user to run `/fsm-setup-hooks` first.

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

   Also copy `src/config.py` and `requirements.txt` if present in the installed package:
   - `~/.claude/scripts/../src/config.py` → `<CWD>/src/config.py` — central pipeline constants (DISPATCH_MODE, MODEL_MAP, HTTP pool, rate-limit). Create `<CWD>/src/` if needed.
   - `~/.claude/scripts/../requirements.txt` → `<CWD>/requirements.txt` — placeholder file (FSM pipeline is stdlib-only). Copy for parity with the installed package; no `pip install` required.

5. **Copy any missing skill files from the package** (if running from within the installed package). Check if `<CWD>/plugins/fsm-workflow/skills/` exists. If it does, copy any missing files into `~/.claude/skills/`:
   - Create `~/.claude/skills/` directory if needed
   - For each of the six skill files, copy from `<CWD>/plugins/fsm-workflow/skills/` to `~/.claude/skills/` only if the target doesn't already exist:
     - `fsm-roles.md`
     - `fsm-task-format.md`
     - `fsm-map-format.md`
     - `fsm-hook-enforcement.md`
     - `model-tier-routing.md`
     - `fsm-workflow-phases.md`
   - This step is idempotent: skips files that already exist in `~/.claude/skills/`. If the package plugins directory doesn't exist (i.e., running from a non-package location), skip this step silently.

6. **Copy any missing skill files to the project** from `~/.claude/skills/` into `<CWD>/.claude/skills/`. Create the directory if it doesn't exist. The six skills are:
   - `~/.claude/skills/fsm-roles.md` → `<CWD>/.claude/skills/fsm-roles.md`
   - `~/.claude/skills/fsm-task-format.md` → `<CWD>/.claude/skills/fsm-task-format.md`
   - `~/.claude/skills/fsm-map-format.md` → `<CWD>/.claude/skills/fsm-map-format.md`
   - `~/.claude/skills/fsm-hook-enforcement.md` → `<CWD>/.claude/skills/fsm-hook-enforcement.md`
   - `~/.claude/skills/model-tier-routing.md` → `<CWD>/.claude/skills/model-tier-routing.md`
   - `~/.claude/skills/fsm-workflow-phases.md` → `<CWD>/.claude/skills/fsm-workflow-phases.md`
   
   Copy each skill file only if the target doesn't already have it, to maintain idempotency.

7. **Verify the install** after doc-writer returns, scripts are copied, and skills are copied:
   - `CLAUDE.md` exists in CWD
   - `.claude/settings.json` exists
   - `.claude/hooks/discipline-gate.sh` exists and is executable
   - `scripts/orchestrate.py`, `scripts/atomize_task.py`, `scripts/audit_discipline.py`, `scripts/check_deps.py`, `scripts/session_close.py` all exist and are executable
   - `src/config.py` exists
   - `requirements.txt` exists
   - `.claude/skills/fsm-roles.md`, `.claude/skills/fsm-task-format.md`, `.claude/skills/fsm-map-format.md`, `.claude/skills/fsm-hook-enforcement.md`, `.claude/skills/model-tier-routing.md`, `.claude/skills/fsm-workflow-phases.md` all exist
   - Report any missing pieces

8. **Confirm to the user:** workflow installed, ready for brainstorming. Suggest next steps: "describe what you want to build, or invoke `spec-writer` to capture an idea. Once you say 'build it', the pipeline auto-dispatches via `PYTHONPATH=. python scripts/orchestrate.py` (one cycle per invocation). The FSM pipeline is stdlib-only; no dependencies to install."
