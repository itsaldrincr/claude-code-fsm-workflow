#!/usr/bin/env python3
"""PreToolUse hook: block direct Agent dispatch of pipeline roles without pending intents.

Pipeline agents (fsm-executor, fsm-integrator, code-fixer, debugger, bug-scanner)
must be dispatched through orchestrate.py's intent queue. This hook denies Agent
calls for those roles when no pending intents exist — forcing the orchestrator to
run orchestrate.py first.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

PIPELINE_ROLES: frozenset[str] = frozenset({
    "fsm-executor",
    "fsm-integrator",
    "code-fixer",
    "debugger",
    "bug-scanner",
})
INTENTS_DIR: str = ".fsm-intents"
RESULTS_DIR: str = ".fsm-results"
MAP_FILENAME: str = "MAP.md"
ORCHESTRATE_SCRIPT: str = "scripts/orchestrate.py"
ACTIONABLE_STATUSES: frozenset[str] = frozenset({
    "PENDING", "IN_PROGRESS", "REVIEW", "EXECUTING",
})


@dataclass(frozen=True)
class AgentCall:
    """Parsed Agent tool input from hook event."""

    subagent_type: str
    cwd: str


def _parse_event(raw: str) -> AgentCall:
    """Extract subagent_type and cwd from the hook JSON payload."""
    data = json.loads(raw)
    tool_input = data.get("tool_input", {})
    return AgentCall(
        subagent_type=tool_input.get("subagent_type", ""),
        cwd=data.get("cwd", str(Path.cwd())),
    )


def _has_actionable_tasks(workspace: Path) -> bool:
    """Return True if MAP.md contains tasks with actionable statuses."""
    map_path = workspace / MAP_FILENAME
    try:
        content = map_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(status in content for status in ACTIONABLE_STATUSES)


def _has_pending_intents(workspace: Path) -> bool:
    """Return True if .fsm-intents/ has files without matching .fsm-results/."""
    intents_dir = workspace / INTENTS_DIR
    results_dir = workspace / RESULTS_DIR
    if not intents_dir.is_dir():
        return False
    for path in intents_dir.glob("*.json"):
        if not (results_dir / path.name).exists():
            return True
    return False


def _deny(reason: str) -> None:
    """Emit a deny decision and flush stdout."""
    payload = {
        "decision": "block",
        "reason": reason,
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def main() -> None:
    """Block pipeline Agent dispatch when no pending intents exist."""
    raw = sys.stdin.read()
    try:
        call = _parse_event(raw)
    except (json.JSONDecodeError, KeyError):
        return

    if call.subagent_type not in PIPELINE_ROLES:
        return

    workspace = Path(call.cwd)
    if not (workspace / ORCHESTRATE_SCRIPT).exists():
        return
    if not _has_actionable_tasks(workspace):
        return

    if _has_pending_intents(workspace):
        return

    _deny(
        f"Direct dispatch of '{call.subagent_type}' blocked. "
        "No pending intents in .fsm-intents/ — run orchestrate.py first. "
        "Use: PYTHONPATH=. python scripts/orchestrate.py (via Bash)."
    )


if __name__ == "__main__":
    main()
