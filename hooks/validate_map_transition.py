#!/usr/bin/env python3
"""PreToolUse hook on Edit targeting MAP.md; blocks invalid state transitions."""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

VALID_TRANSITIONS: Dict[str, set[str]] = {
    "PENDING": {"IN_PROGRESS"},
    "IN_PROGRESS": {"REVIEW", "EXECUTING", "DONE", "FAILED", "PARTIAL"},
    "EXECUTING": {"VERIFY", "FAILED"},
    "VERIFY": {"DONE", "FAILED"},
    "REVIEW": {"DONE", "IN_PROGRESS", "BLOCKED"},
    "FAILED": {"IN_PROGRESS"},
    "PARTIAL": {"IN_PROGRESS"},
    "DONE": set(),
    "BLOCKED": set(),
}

STATE_PATTERN = re.compile(r"\.{2,}\s+(PENDING|IN_PROGRESS|EXECUTING|VERIFY|REVIEW|DONE|FAILED|PARTIAL|BLOCKED)\b")


@dataclass
class HookInput:
    """Parsed fields from a Claude Code PreToolUse hook event on Edit."""

    tool_name: str
    file_path: str
    old_string: str
    new_string: str


@dataclass
class TransitionCheck:
    """Extracted state transition to validate."""

    old_status: str
    new_status: str


def _parse_hook_input(raw: str) -> HookInput:
    """Parse hook event JSON from stdin into a HookInput."""
    try:
        data: Dict[str, Any] = json.loads(raw)
        tool_input: Dict[str, Any] = data.get("toolInput", data.get("tool_input", {}))
        return HookInput(
            tool_name=tool_input.get("tool_name", ""),
            file_path=tool_input.get("file_path", ""),
            old_string=tool_input.get("old_string", ""),
            new_string=tool_input.get("new_string", ""),
        )
    except Exception as exc:
        # Intentional safe-default: allow edits on parse failure rather than blocking
        logging.getLogger(__name__).warning("Malformed hook input (allowing edit): %s", exc)
        return HookInput(tool_name="", file_path="", old_string="", new_string="")


def _extract_transition(hook_input: HookInput) -> Optional[TransitionCheck]:
    """Extract state transition from old and new strings using regex."""
    old_match = STATE_PATTERN.search(hook_input.old_string)
    new_match = STATE_PATTERN.search(hook_input.new_string)

    # Both must contain status tokens for a transition check.
    # Single-sided matches (add/remove lines) are not state transitions.
    if old_match and new_match:
        return TransitionCheck(old_status=old_match.group(1), new_status=new_match.group(1))
    return None


def _check_transition(check: TransitionCheck) -> bool:
    """Return True if new_status is valid given old_status."""
    if check.old_status not in VALID_TRANSITIONS:
        return True
    return check.new_status in VALID_TRANSITIONS[check.old_status]


def _emit_deny(reason: str) -> None:
    """Output hookSpecificOutput JSON with permissionDecision: deny."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _emit_allow() -> None:
    """Output hookSpecificOutput JSON with permissionDecision: allow."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "",
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _build_denial_reason(check: TransitionCheck) -> str:
    """Build the denial reason string."""
    valid = VALID_TRANSITIONS.get(check.old_status, set())
    return (
        f"Invalid MAP.md state transition: {check.old_status} → "
        f"{check.new_status}. Valid next states: {', '.join(valid)}"
    )


def _dispatch_on_map_edit(hook_input: HookInput) -> None:
    """Check MAP.md transition; emit deny or allow."""
    if not hook_input.file_path.endswith("MAP.md"):
        _emit_allow()
        return
    transition = _extract_transition(hook_input)
    if transition is None or _check_transition(transition):
        _emit_allow()
        return
    _emit_deny(_build_denial_reason(transition))


def main() -> None:
    """Entry point: parse stdin, dispatch on file type."""
    raw = sys.stdin.read()
    _dispatch_on_map_edit(_parse_hook_input(raw))


if __name__ == "__main__":
    main()
