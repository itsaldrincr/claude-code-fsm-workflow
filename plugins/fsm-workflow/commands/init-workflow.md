---
description: Bootstrap the FSM agent workflow in the current directory — installs CLAUDE.md, project hooks, and the discipline gate.
---

The user wants the FSM workflow installed in the current working directory. Execute the bootstrap directly — this is a one-shot setup, no dispatcher needed.

## Steps

1. **Check whether a workflow already exists.** Run `ls CLAUDE.md .claude/settings.json 2>/dev/null` in the CWD. If both exist, STOP and report "workflow already installed — nothing to do." If only one exists, ask whether to overwrite or merge.

2. **Dispatch `doc-writer` in pre-workflow mode** with this exact prompt:

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

3. **Verify the install** after doc-writer returns:
   - `CLAUDE.md` exists in CWD
   - `.claude/settings.json` exists
   - `.claude/hooks/discipline-gate.sh` exists and is executable
   - Report any missing pieces

4. **Confirm to the user:** workflow installed, ready for brainstorming. Suggest next steps: "describe what you want to build, or invoke `spec-writer` to capture an idea."
