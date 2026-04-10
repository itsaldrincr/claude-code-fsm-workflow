#!/usr/bin/env python3
"""PostToolUse hook for Read of MAP.md: nudge toward orchestrate.py when actionable tasks exist."""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

ORCHESTRATE_SCRIPT: str = "scripts/orchestrate.py"
NUDGE_STATES: set[str] = {"PENDING", "REVIEW"}


@dataclass
class HookEvent:
    """Parsed hook event from stdin."""

    tool_name: str
    file_path: str
    tool_output: str


@dataclass
class NudgeCheck:
    """Result of nudge eligibility check."""

    has_actionable: bool
    orchestrate_exists: bool


def _parse_hook_event(raw: str) -> HookEvent:
    """Extract tool_name, file_path, tool_output from hook event JSON."""
    data: Dict[str, Any] = json.loads(raw)
    tool_input: Dict[str, Any] = data.get("toolInput", data.get("tool_input", {}))
    tool_response = data.get("tool_response", data.get("toolResponse", {}))
    tool_output: str = tool_response if isinstance(tool_response, str) else tool_response.get("content", "")
    file_path_str: str = tool_input.get("file_path", "")
    return HookEvent(
        tool_name=data.get("toolName", data.get("tool_name", "")),
        file_path=file_path_str,
        tool_output=tool_output,
    )


def _has_actionable_tasks(tool_output: str) -> bool:
    """Check if output contains any PENDING or REVIEW status markers."""
    pattern = r"\.{2,}\s+(PENDING|REVIEW)\b"
    return bool(re.search(pattern, tool_output))


def _check_orchestrate_exists(cwd: str) -> bool:
    """Return whether scripts/orchestrate.py exists in cwd."""
    orchestrate_path = Path(cwd) / ORCHESTRATE_SCRIPT
    return orchestrate_path.exists()


def _build_nudge_message() -> str:
    """Return the nudge text."""
    return "MAP.md has PENDING or REVIEW tasks. Run: python scripts/orchestrate.py"


def _emit_nudge(message: str) -> None:
    """Output hookSpecificOutput JSON with additionalContext."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _extract_cwd(raw: str) -> str:
    """Extract CWD from hook event JSON, falling back to Path.cwd()."""
    try:
        data = json.loads(raw)
        return data.get("cwd", str(Path.cwd()))
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to parse cwd from hook event: %s", exc)
        return str(Path.cwd())


def main() -> None:
    """Entry point: read stdin, check conditions, emit nudge or exit silently."""
    raw = sys.stdin.read()
    try:
        event = _parse_hook_event(raw)
    except Exception as exc:
        logging.getLogger(__name__).debug("Hook error: %s", exc)
        return

    if not event.file_path.endswith("MAP.md"):
        return

    cwd = _extract_cwd(raw)
    check = NudgeCheck(
        has_actionable=_has_actionable_tasks(event.tool_output),
        orchestrate_exists=_check_orchestrate_exists(cwd),
    )
    if not check.has_actionable or not check.orchestrate_exists:
        return

    _emit_nudge(_build_nudge_message())


if __name__ == "__main__":
    main()
