"""Tests for src/fsm_core/trace.py — AC2.1, AC2.2, AC2.3."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.fsm_core.trace import (
    AppendRequest,
    TraceEvent,
    append_event,
    build_event_from_stdin,
)

SESSION_ID_AC21 = "test-session-ac21"
SESSION_ID_AC23 = "test-session-ac23"
EVENT_TYPE_TEST = "PostToolUse"

TRACE_EVENT_FIELDS = {
    "session_id",
    "timestamp",
    "event_type",
    "agent_type",
    "tool_name",
    "tool_input_summary",
    "tool_result_status",
    "hook_decision",
    "decision_reason",
}


def _make_trace_event(session_id: str) -> TraceEvent:
    """Build a synthetic TraceEvent for testing."""
    return TraceEvent(
        session_id=session_id,
        timestamp="2026-04-08T00:00:00+00:00",
        event_type=EVENT_TYPE_TEST,
        agent_type=None,
        tool_name="Bash",
        tool_input_summary='{"cmd": "ls"}',
        tool_result_status="ok",
        hook_decision="n/a",
        decision_reason="",
    )


def _make_append_request(event: TraceEvent, base_dir: Path) -> AppendRequest:
    """Wrap event + base_dir into AppendRequest."""
    return AppendRequest(event=event, base_dir=base_dir)


class TestEventProducesParseableLine(unittest.TestCase):
    """AC2.1 — single event produces parseable JSONL with all 9 fields."""

    def test_event_produces_parseable_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            event = _make_trace_event(SESSION_ID_AC21)
            append_event(_make_append_request(event, base_dir))
            log_file = base_dir / SESSION_ID_AC21 / f"{EVENT_TYPE_TEST}.jsonl"
            self.assertTrue(log_file.exists(), "JSONL file must be created")
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed.keys() & TRACE_EVENT_FIELDS, TRACE_EVENT_FIELDS)


class TestOsErrorDoesNotPropagate(unittest.TestCase):
    """AC2.2 — OSError in append_event does not propagate; stderr gets output."""

    def test_oserror_does_not_propagate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            event = _make_trace_event(SESSION_ID_AC21)
            request = _make_append_request(event, base_dir)
            with patch("builtins.open", side_effect=OSError("disk full")):
                captured: list[str] = []
                original_stderr_write = sys.stderr.write

                def _capture(s: str) -> int:
                    captured.append(s)
                    return original_stderr_write(s)

                sys.stderr.write = _capture  # type: ignore[method-assign]
                try:
                    append_event(request)
                finally:
                    sys.stderr.write = original_stderr_write  # type: ignore[method-assign]

            self.assertTrue(
                any("OSError" in chunk or "disk full" in chunk for chunk in captured),
                "stderr must contain OSError output",
            )


class TestReplayNoLossNoDupes(unittest.TestCase):
    """AC2.3 — 100 events → exactly 100 lines in the JSONL file."""

    def test_replay_no_loss_no_dupes(self) -> None:
        EVENT_COUNT = 100
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            for _ in range(EVENT_COUNT):
                event = _make_trace_event(SESSION_ID_AC23)
                append_event(_make_append_request(event, base_dir))
            log_file = base_dir / SESSION_ID_AC23 / f"{EVENT_TYPE_TEST}.jsonl"
            self.assertTrue(log_file.exists())
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), EVENT_COUNT)


class TestBuildEventFromStdin(unittest.TestCase):
    """Unit tests for build_event_from_stdin field extraction."""

    def _make_raw(self, overrides: dict) -> str:
        base = {
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"path": "/tmp/x"},
        }
        base.update(overrides)
        return json.dumps(base)

    def test_basic_extraction(self) -> None:
        event = build_event_from_stdin(self._make_raw({}))
        self.assertEqual(event.session_id, "s1")
        self.assertEqual(event.event_type, "PreToolUse")
        self.assertEqual(event.tool_name, "Read")
        self.assertEqual(event.tool_result_status, "unknown")
        self.assertEqual(event.hook_decision, "n/a")

    def test_tool_result_status_error(self) -> None:
        raw = self._make_raw({"tool_response": {"type": "error"}})
        event = build_event_from_stdin(raw)
        self.assertEqual(event.tool_result_status, "error")

    def test_tool_result_status_blocked(self) -> None:
        raw = self._make_raw({"tool_response": {"decision": "block"}})
        event = build_event_from_stdin(raw)
        self.assertEqual(event.tool_result_status, "blocked")

    def test_agent_type_none_when_absent(self) -> None:
        event = build_event_from_stdin(self._make_raw({}))
        self.assertIsNone(event.agent_type)


if __name__ == "__main__":
    unittest.main()
