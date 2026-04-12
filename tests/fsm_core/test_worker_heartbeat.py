import json
import os
from pathlib import Path
from unittest.mock import patch

from src.fsm_core.worker_heartbeat import WriteHeartbeatRequest
from src.fsm_core.worker_heartbeat import write_heartbeat


def test_write_heartbeat_creates_file_with_expected_keys(tmp_path: Path) -> None:
    """Call write_heartbeat, load the file, assert JSON contains required keys."""
    request = WriteHeartbeatRequest(
        task_id="task_123",
        workspace=tmp_path,
        tool_count=5,
        dispatch_mode="fsm-executor",
    )

    write_heartbeat(request)

    hb_file = tmp_path / ".fsm-worker-hb" / "task_123.json"
    assert hb_file.exists()

    with open(hb_file) as f:
        data = json.load(f)

    assert "task_id" in data
    assert "last_hb_iso" in data
    assert "tool_count" in data
    assert "dispatch_mode" in data
    assert data["task_id"] == "task_123"
    assert data["tool_count"] == 5
    assert data["dispatch_mode"] == "fsm-executor"


def test_write_heartbeat_is_atomic_via_tmp_rename(tmp_path: Path) -> None:
    """Monkeypatch os.replace to count calls, assert it was invoked."""
    request = WriteHeartbeatRequest(
        task_id="task_456",
        workspace=tmp_path,
        tool_count=3,
        dispatch_mode="fsm-integrator",
    )

    replace_calls = []

    original_replace = os.replace

    def mock_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        original_replace(src, dst)

    with patch("src.fsm_core.worker_heartbeat.os.replace", side_effect=mock_replace):
        write_heartbeat(request)

    assert len(replace_calls) == 1
    src, dst = replace_calls[0]
    assert str(src).endswith(".tmp")
    assert str(dst) == str(tmp_path / ".fsm-worker-hb" / "task_456.json")


def test_write_heartbeat_creates_parent_dir(tmp_path: Path) -> None:
    """Point at an empty workspace, assert the .fsm-worker-hb/ dir is created automatically."""
    empty_workspace = tmp_path / "empty"
    empty_workspace.mkdir()

    assert not (empty_workspace / ".fsm-worker-hb").exists()

    request = WriteHeartbeatRequest(
        task_id="task_789",
        workspace=empty_workspace,
        tool_count=2,
        dispatch_mode="fsm-executor",
    )

    write_heartbeat(request)

    hb_dir = empty_workspace / ".fsm-worker-hb"
    assert hb_dir.exists()
    assert hb_dir.is_dir()
    assert (hb_dir / "task_789.json").exists()
