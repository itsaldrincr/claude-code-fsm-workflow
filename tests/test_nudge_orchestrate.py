#!/usr/bin/env python3
"""Tests for nudge_orchestrate hook."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from hooks.nudge_orchestrate import (
    HookEvent,
    NudgeCheck,
    _build_nudge_message,
    _check_orchestrate_exists,
    _has_actionable_tasks,
    _parse_hook_event,
)


class TestParseHookEvent:
    """Tests for _parse_hook_event."""

    def test_parse_standard_format(self) -> None:
        """Parse hook event with standard field names."""
        raw = json.dumps(
            {
                "toolName": "Read",
                "toolInput": {"file_path": "/tmp/MAP.md"},
                "tool_response": {"content": "Some output"},
            }
        )
        result = _parse_hook_event(raw)
        assert result.tool_name == "Read"
        assert result.file_path == "/tmp/MAP.md"
        assert result.tool_output == "Some output"

    def test_parse_alternative_format(self) -> None:
        """Parse hook event with snake_case field names."""
        raw = json.dumps(
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/tmp/MAP.md"},
                "tool_output": "content",
            }
        )
        result = _parse_hook_event(raw)
        assert result.tool_name == "Read"
        assert result.file_path == "/tmp/MAP.md"

    def test_parse_missing_fields(self) -> None:
        """Parse event with missing optional fields."""
        raw = json.dumps({})
        result = _parse_hook_event(raw)
        assert result.tool_name == ""
        assert result.file_path == ""
        assert result.tool_output == ""


class TestHasActionableTasks:
    """Tests for _has_actionable_tasks."""

    def test_detects_pending(self) -> None:
        """Detect PENDING status marker."""
        output = "[task_foo.md] ......... PENDING"
        assert _has_actionable_tasks(output) is True

    def test_detects_review(self) -> None:
        """Detect REVIEW status marker."""
        output = "[task_foo.md] ......... REVIEW"
        assert _has_actionable_tasks(output) is True

    def test_detects_with_whitespace(self) -> None:
        """Detect with various whitespace patterns."""
        output = "[task_foo.md] ...  PENDING"
        assert _has_actionable_tasks(output) is True

    def test_ignores_done(self) -> None:
        """Return False when only DONE status present."""
        output = "[task_foo.md] ......... DONE"
        assert _has_actionable_tasks(output) is False

    def test_empty_output(self) -> None:
        """Return False for empty output."""
        assert _has_actionable_tasks("") is False

    def test_no_matching_pattern(self) -> None:
        """Return False when no pattern matches."""
        output = "some random text with PENDING in it"
        assert _has_actionable_tasks(output) is False

    def test_multiple_states(self) -> None:
        """Detect when multiple states present with actionable."""
        output = "[task_foo.md] ......... DONE\n[task_bar.md] ......... PENDING"
        assert _has_actionable_tasks(output) is True


class TestCheckOrchestrateExists:
    """Tests for _check_orchestrate_exists."""

    def test_exists_returns_true(self) -> None:
        """Return True when orchestrate.py exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts_dir = Path(tmpdir) / "scripts"
            scripts_dir.mkdir()
            orchestrate_file = scripts_dir / "orchestrate.py"
            orchestrate_file.touch()
            assert _check_orchestrate_exists(tmpdir) is True

    def test_missing_returns_false(self) -> None:
        """Return False when orchestrate.py does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            assert _check_orchestrate_exists(tmpdir) is False

    def test_exists_in_subdirectory(self) -> None:
        """Correctly resolve scripts/orchestrate.py in cwd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts", "orchestrate.py").touch()
            assert _check_orchestrate_exists(tmpdir) is True


class TestBuildNudgeMessage:
    """Tests for _build_nudge_message."""

    def test_message_content(self) -> None:
        """Return correct nudge message."""
        msg = _build_nudge_message()
        assert "MAP.md has PENDING or REVIEW tasks" in msg
        assert "python scripts/orchestrate.py" in msg


class TestNudgeCheckDataclass:
    """Tests for NudgeCheck dataclass."""

    def test_instantiate(self) -> None:
        """Create NudgeCheck instance."""
        check = NudgeCheck(has_actionable=True, orchestrate_exists=True)
        assert check.has_actionable is True
        assert check.orchestrate_exists is True

    def test_both_false(self) -> None:
        """Create NudgeCheck with both False."""
        check = NudgeCheck(has_actionable=False, orchestrate_exists=False)
        assert check.has_actionable is False
        assert check.orchestrate_exists is False


class TestIntegration:
    """Integration tests for full nudge flow."""

    def test_nudge_when_conditions_met(self) -> None:
        """Emit nudge when all conditions are met."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts", "orchestrate.py").touch()

            with mock.patch("sys.stdout.write") as mock_write:
                with mock.patch("sys.stdout.flush"):
                    raw = json.dumps(
                        {
                            "toolInput": {"file_path": "MAP.md"},
                            "tool_response": {"content": "[task_foo.md] ......... PENDING"},
                        }
                    )
                    with mock.patch("sys.stdin.read", return_value=raw):
                        with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                            from hooks.nudge_orchestrate import main

                            main()
                            mock_write.assert_called_once()

    def test_no_nudge_for_non_map_file(self) -> None:
        """Silent when file is not MAP.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts", "orchestrate.py").touch()

            with mock.patch("sys.stdout.write") as mock_write:
                raw = json.dumps(
                    {
                        "toolInput": {"file_path": "other.md"},
                        "tool_response": {"content": "[task_foo.md] ......... PENDING"},
                    }
                )
                with mock.patch("sys.stdin.read", return_value=raw):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from hooks.nudge_orchestrate import main

                        main()
                        mock_write.assert_not_called()

    def test_no_nudge_when_all_done(self) -> None:
        """Silent when all tasks are DONE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts", "orchestrate.py").touch()

            with mock.patch("sys.stdout.write") as mock_write:
                raw = json.dumps(
                    {
                        "toolInput": {"file_path": "MAP.md"},
                        "tool_response": {"content": "[task_foo.md] ......... DONE"},
                    }
                )
                with mock.patch("sys.stdin.read", return_value=raw):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from hooks.nudge_orchestrate import main

                        main()
                        mock_write.assert_not_called()

    def test_no_nudge_when_orchestrate_missing(self) -> None:
        """Silent when orchestrate.py does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("sys.stdout.write") as mock_write:
                raw = json.dumps(
                    {
                        "toolInput": {"file_path": "MAP.md"},
                        "tool_response": {"content": "[task_foo.md] ......... PENDING"},
                    }
                )
                with mock.patch("sys.stdin.read", return_value=raw):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from hooks.nudge_orchestrate import main

                        main()
                        mock_write.assert_not_called()

    def test_no_nudge_for_empty_output(self) -> None:
        """Silent when MAP.md output is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "scripts").mkdir()
            Path(tmpdir, "scripts", "orchestrate.py").touch()

            with mock.patch("sys.stdout.write") as mock_write:
                raw = json.dumps(
                    {
                        "toolInput": {"file_path": "MAP.md"},
                        "tool_response": {"content": ""},
                    }
                )
                with mock.patch("sys.stdin.read", return_value=raw):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(tmpdir)):
                        from hooks.nudge_orchestrate import main

                        main()
                        mock_write.assert_not_called()
