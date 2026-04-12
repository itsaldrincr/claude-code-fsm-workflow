---
description: Bootstrap the FSM agent workflow in the current directory — installs CLAUDE.md, project hooks, the discipline gate, and orchestrator scripts.
---

The user wants the FSM workflow installed in the current working directory. Execute the bootstrap directly — this is a one-shot setup, no dispatcher needed.

## Prerequisites

This command depends on `~/.claude/templates/`, `~/.claude/scripts/`, `~/.claude/src/`, and `~/.claude/skills/` existing — all are populated by `/fsm-setup-hooks` (which runs `install.sh`). The `~/.claude/skills/` directory should contain:
  - `fsm-roles.md`
  - `fsm-task-format.md`
  - `fsm-map-format.md`
  - `fsm-hook-enforcement.md`
  - `model-tier-routing.md`
  - `fsm-workflow-phases.md`

If any are missing, tell the user to run `/fsm-setup-hooks` first and stop.

## Steps

1. **Check whether a workflow already exists.** Run `ls CLAUDE.md .claude/settings.json 2>/dev/null` in the CWD. If both exist, STOP and report "workflow already installed — nothing to do." If only one exists, ask whether to overwrite or merge.

2. **Check prerequisites.** Run `ls ~/.claude/templates/CLAUDE.md ~/.claude/scripts/orchestrate.py ~/.claude/src/config.py ~/.claude/src/fsm_core/action_decider.py ~/.claude/requirements.txt ~/.claude/skills/fsm-roles.md ~/.claude/skills/fsm-task-format.md ~/.claude/skills/fsm-map-format.md ~/.claude/skills/fsm-hook-enforcement.md ~/.claude/skills/model-tier-routing.md ~/.claude/skills/fsm-workflow-phases.md 2>&1`. If any are missing, STOP and tell the user to run `/fsm-setup-hooks` first.

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

4. **Copy orchestrator scripts** from `~/.claude/scripts/` into `<CWD>/scripts/`. Create the directory if it doesn't exist. Copy only if the target doesn't already have them:
   - `~/.claude/scripts/orchestrate.py` → `<CWD>/scripts/orchestrate.py` — automated dispatch loop
   - `~/.claude/scripts/atomize_task.py` → `<CWD>/scripts/atomize_task.py` — mandatory task atomizer
   - `~/.claude/scripts/audit_discipline.py` → `<CWD>/scripts/audit_discipline.py` — AST discipline checker
   - `~/.claude/scripts/check_deps.py` → `<CWD>/scripts/check_deps.py` — import resolution checker
   - `~/.claude/scripts/session_close.py` → `<CWD>/scripts/session_close.py` — test-gated cleanup
   - `~/.claude/scripts/claude_session_driver.py` → `<CWD>/scripts/claude_session_driver.py` — intent/result driver bridge

   **Copy the `src/` package** (orchestrate.py's runtime dependencies). These modules are required — orchestrate.py will fail with `ModuleNotFoundError` without them:
   - `~/.claude/src/__init__.py` → `<CWD>/src/__init__.py`
   - `~/.claude/src/config.py` → `<CWD>/src/config.py` — central pipeline constants
   - `~/.claude/src/fsm_core/` → `<CWD>/src/fsm_core/` — copy the entire directory (all `*.py` files). Key modules: `action_decider.py`, `map_io.py`, `map_reader.py`, `map_lock.py`, `advisor_cache.py`, `advisor_parser.py`, `auto_heal.py`, `claude_session_backend.py`, `dispatch_contract.py`, `dispatch_router.py`, `frontmatter.py`, `orchestrate_lock.py`, `session_state.py`, `startup_checks.py`, `trace.py`, `wave_deterministic_gate.py`, `worker_heartbeat.py`, `dag_waves.py`.
   
   Create `<CWD>/src/` and `<CWD>/src/fsm_core/` directories if needed. Skip files that already exist.

   **Copy `requirements.txt`:**
   - `~/.claude/requirements.txt` → `<CWD>/requirements.txt` — single dep: `anthropic>=0.40`. After copying, prompt the user to run `pip install -r requirements.txt` if they haven't already.

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
   - `scripts/orchestrate.py`, `scripts/atomize_task.py`, `scripts/audit_discipline.py`, `scripts/check_deps.py`, `scripts/session_close.py`, `scripts/claude_session_driver.py` all exist
   - `src/__init__.py`, `src/config.py` exist
   - `src/fsm_core/__init__.py` exists and `src/fsm_core/` contains at least 15 `.py` modules (action_decider, map_io, map_reader, etc.)
   - `requirements.txt` exists
   - `.claude/skills/fsm-roles.md`, `.claude/skills/fsm-task-format.md`, `.claude/skills/fsm-map-format.md`, `.claude/skills/fsm-hook-enforcement.md`, `.claude/skills/model-tier-routing.md`, `.claude/skills/fsm-workflow-phases.md` all exist
   - Report any missing pieces

8. **Confirm to the user:** workflow installed, ready for brainstorming. Suggest next steps: "describe what you want to build, or invoke `spec-writer` to capture an idea. Once you say 'build it', the pipeline auto-dispatches via `python scripts/orchestrate.py` (one-shot) or `python scripts/orchestrate.py --daemon` (persistent). If you haven't installed dependencies yet, run `pip install -r requirements.txt` first."
