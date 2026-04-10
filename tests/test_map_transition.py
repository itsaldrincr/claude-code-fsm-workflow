"""Tests for validate_map_transition hook."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest


HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "validate_map_transition.py"


@dataclass
class _HookEventInput:
    """Input to _make_hook_event."""

    file_path: str
    old_string: str
    new_string: str


def _run_hook(hook_input: dict) -> dict:
    """Invoke the hook script with JSON input and return parsed JSON response."""
    json_input = json.dumps(hook_input)
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json_input,
        capture_output=True,
        text=True,
    )
    if not result.stdout:
        return {}
    return json.loads(result.stdout)


def _make_hook_event(input_data: _HookEventInput) -> dict:
    """Build a hook event with toolInput for Edit."""
    return {
        "toolInput": {
            "file_path": input_data.file_path,
            "old_string": input_data.old_string,
            "new_string": input_data.new_string,
        }
    }


class TestValidTransitions:
    """Tests for allowed state transitions."""

    def test_pending_to_in_progress(self) -> None:
        """PENDING -> IN_PROGRESS is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_in_progress_to_executing(self) -> None:
        """IN_PROGRESS -> EXECUTING is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... IN_PROGRESS",
            "[task_foo.md] ......... EXECUTING",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_in_progress_to_failed(self) -> None:
        """IN_PROGRESS -> FAILED is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... IN_PROGRESS",
            "[task_foo.md] ......... FAILED",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_in_progress_to_partial(self) -> None:
        """IN_PROGRESS -> PARTIAL is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... IN_PROGRESS",
            "[task_foo.md] ......... PARTIAL",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_executing_to_verify(self) -> None:
        """EXECUTING -> VERIFY is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... EXECUTING",
            "[task_foo.md] ......... VERIFY",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_verify_to_done(self) -> None:
        """VERIFY -> DONE is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... VERIFY",
            "[task_foo.md] ......... DONE",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_partial_to_in_progress(self) -> None:
        """PARTIAL -> IN_PROGRESS is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PARTIAL",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_failed_to_in_progress(self) -> None:
        """FAILED -> IN_PROGRESS is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... FAILED",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_review_to_done(self) -> None:
        """REVIEW -> DONE is allowed."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... REVIEW",
            "[task_foo.md] ......... DONE",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestInvalidTransitions:
    """Tests for blocked state transitions."""

    def test_pending_to_review(self) -> None:
        """PENDING -> REVIEW is blocked."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... REVIEW",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "PENDING" in resp["hookSpecificOutput"]["permissionDecisionReason"]

    def test_pending_to_done(self) -> None:
        """PENDING -> DONE is blocked."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... DONE",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_done_to_in_progress(self) -> None:
        """DONE -> IN_PROGRESS is blocked."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... DONE",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_done_to_any(self) -> None:
        """DONE -> any state is blocked."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... DONE",
            "[task_foo.md] ......... FAILED",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_blocked_to_in_progress(self) -> None:
        """BLOCKED -> IN_PROGRESS is blocked."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... BLOCKED",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestEdgeCases:
    """Tests for edge cases: non-MAP.md, malformed input, no pattern match."""

    def test_non_map_file_passes_through(self) -> None:
        """Edits to non-MAP.md files are allowed."""
        event = _make_hook_event(_HookEventInput(
            "src/config.ts",
            "state: PENDING",
            "state: IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_malformed_json_passes_through(self) -> None:
        """Malformed JSON input does not crash; hook passes through."""
        result = subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input="not valid json",
            capture_output=True,
            text=True,
        )
        if result.stdout:
            resp = json.loads(result.stdout)
            assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_no_status_pattern_passes_through(self) -> None:
        """Edits with no state pattern in old_string or new_string pass through."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "some other content",
            "other changed content",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_only_old_status_pattern_passes_through(self) -> None:
        """If only old_string has pattern, pass through."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "state: PENDING",
            "state: changed",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_only_new_status_pattern_passes_through(self) -> None:
        """If only new_string has pattern, pass through."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "state: changed",
            "state: IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_state_frontmatter_pattern(self) -> None:
        """State: dot-padding format is recognized."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... IN_PROGRESS",
        ))
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_empty_file_path(self) -> None:
        """Missing file_path in toolInput passes through."""
        event = {
            "toolInput": {
                "old_string": "status ... PENDING",
                "new_string": "status ... IN_PROGRESS",
            }
        }
        resp = _run_hook(event)
        assert resp["hookSpecificOutput"]["permissionDecision"] == "allow"


class TestReasonMessages:
    """Tests for denial reason messages."""

    def test_denial_reason_includes_states(self) -> None:
        """Denial reason includes old and new state."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... DONE",
        ))
        resp = _run_hook(event)
        reason = resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "PENDING" in reason
        assert "DONE" in reason

    def test_denial_reason_lists_valid_next_states(self) -> None:
        """Denial reason lists valid next states."""
        event = _make_hook_event(_HookEventInput(
            "MAP.md",
            "[task_foo.md] ......... PENDING",
            "[task_foo.md] ......... DONE",
        ))
        resp = _run_hook(event)
        reason = resp["hookSpecificOutput"]["permissionDecisionReason"]
        assert "IN_PROGRESS" in reason
