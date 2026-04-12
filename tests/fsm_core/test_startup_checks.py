from pathlib import Path

import pytest

from src.fsm_core.startup_checks import (
    find_state_drifts,
    resolve_dispatch_mode,
    sync_task_states_to_map,
)


MAP_CONTENT = """\
# MAP

## Active Tasks

### Wave 1
project/
  src/  [task_001_demo.md] .......... FAILED
"""

TASK_CONTENT = """\
---
id: task_001
name: demo
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: abc123
created: 2026-04-12
---

## Files
Creates:
  demo.py
"""


def _write_workspace(root: Path) -> None:
    (root / "MAP.md").write_text(MAP_CONTENT, encoding="utf-8")
    (root / "task_001_demo.md").write_text(TASK_CONTENT, encoding="utf-8")


class TestResolveDispatchMode:
    def test_keeps_claude_session_mode(self) -> None:
        assert resolve_dispatch_mode("claude_session") == "claude_session"

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve_dispatch_mode("invalid_mode")


class TestMapTaskStateReconcile:
    def test_detects_map_task_state_drift(self, tmp_path: Path) -> None:
        _write_workspace(tmp_path)
        drifts = find_state_drifts(tmp_path, tmp_path / "MAP.md")
        assert len(drifts) == 1
        assert drifts[0].task_id == "task_001"
        assert drifts[0].map_status == "FAILED"
        assert drifts[0].task_state == "PENDING"

    def test_sync_rewrites_task_state_to_map(self, tmp_path: Path) -> None:
        _write_workspace(tmp_path)
        drifts = find_state_drifts(tmp_path, tmp_path / "MAP.md")
        changed = sync_task_states_to_map(drifts)
        assert changed == 1
        post = find_state_drifts(tmp_path, tmp_path / "MAP.md")
        assert post == []
        content = (tmp_path / "task_001_demo.md").read_text(encoding="utf-8")
        assert "state: FAILED" in content
