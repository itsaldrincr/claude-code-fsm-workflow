"""Tests for the enforce_orchestrate PreToolUse hook."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = str(Path(__file__).resolve().parent.parent / "hooks" / "enforce_orchestrate.py")


def _run_hook(payload: dict) -> str:
    """Run the hook script with a JSON payload on stdin."""
    result = subprocess.run(
        [sys.executable, HOOK_PATH],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout


def _make_payload(subagent_type: str, cwd: str) -> dict:
    """Build a minimal Agent PreToolUse hook event."""
    return {
        "tool_input": {"subagent_type": subagent_type},
        "cwd": cwd,
    }


class TestEnforceOrchestrate:
    """Verify pipeline roles are blocked without pending intents."""

    def test_allows_non_pipeline_role(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        output = _run_hook(_make_payload("explore-scout", str(tmp_path)))
        assert output == ""

    def test_allows_when_no_map(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        output = _run_hook(_make_payload("fsm-executor", str(tmp_path)))
        assert output == ""

    def test_allows_when_no_orchestrate(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        output = _run_hook(_make_payload("fsm-executor", str(tmp_path)))
        assert output == ""

    def test_blocks_executor_without_intents(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        output = _run_hook(_make_payload("fsm-executor", str(tmp_path)))
        result = json.loads(output)
        assert result["decision"] == "block"
        assert "orchestrate.py" in result["reason"]

    def test_blocks_all_pipeline_roles(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        for role in ("fsm-executor", "fsm-integrator", "code-fixer", "debugger", "bug-scanner"):
            output = _run_hook(_make_payload(role, str(tmp_path)))
            result = json.loads(output)
            assert result["decision"] == "block", f"{role} should be blocked"

    def test_allows_with_pending_intents(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        (tmp_path / ".fsm-intents").mkdir()
        (tmp_path / ".fsm-intents" / "intent_abc.json").write_text("{}")
        output = _run_hook(_make_payload("fsm-executor", str(tmp_path)))
        assert output == ""

    def test_blocks_when_all_intents_have_results(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        (tmp_path / ".fsm-intents").mkdir()
        (tmp_path / ".fsm-intents" / "intent_abc.json").write_text("{}")
        (tmp_path / ".fsm-results").mkdir()
        (tmp_path / ".fsm-results" / "intent_abc.json").write_text("{}")
        output = _run_hook(_make_payload("fsm-executor", str(tmp_path)))
        result = json.loads(output)
        assert result["decision"] == "block"

    def test_allows_empty_subagent_type(self, tmp_path: Path) -> None:
        (tmp_path / "MAP.md").write_text("... PENDING\n")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "orchestrate.py").touch()
        output = _run_hook(_make_payload("", str(tmp_path)))
        assert output == ""
