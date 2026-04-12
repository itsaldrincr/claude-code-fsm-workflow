import json
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest

from src.config import WORKER_HEARTBEAT_STALE_SECONDS
from src.fsm_core.auto_heal import heal_stale_in_progress
from src.fsm_core.worker_heartbeat import WriteHeartbeatRequest
from src.fsm_core.worker_heartbeat import write_heartbeat


def _write_map_with_task(tmp_path: Path, task_id: str) -> Path:
    """Write synthetic MAP.md with one IN_PROGRESS task."""
    map_path = tmp_path / "MAP.md"
    content = f"""\
# MAP

## Active Tasks

### Wave 1
Project/
  src/engine/      [{task_id}_test.md] ........ IN_PROGRESS
"""
    map_path.write_text(content, encoding="utf-8")
    return map_path


def _make_task_content() -> str:
    """Return minimal task file frontmatter content."""
    return """\
---
id: task_test
name: test_task
state: IN_PROGRESS
step: 1 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: 123456
created: 2026-04-12
---

## Files
Reads:
  dummy.txt

## Program
1. Dummy step

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] Test

## Transition Rules
"""


def _write_task_file(tmp_path: Path, task_id: str) -> Path:
    """Write minimal task file with required frontmatter."""
    task_path = tmp_path / f"{task_id}_test.md"
    task_path.write_text(_make_task_content(), encoding="utf-8")
    return task_path


@dataclass(frozen=True, slots=True)
class _BackdateParams:
    """Parameters for backdating a heartbeat."""

    tmp_path: Path
    task_id: str
    age_seconds: int


def _backdate_heartbeat(workspace: Path, request: _BackdateParams) -> None:
    """Set a heartbeat's last_hb_iso to N seconds in the past."""
    hb_path = workspace / ".fsm-worker-hb" / f"{request.task_id}.json"
    old_time = datetime.now(timezone.utc) - timedelta(seconds=request.age_seconds)
    hb_data = json.loads(hb_path.read_text(encoding="utf-8"))
    hb_data["last_hb_iso"] = old_time.isoformat()
    hb_path.write_text(json.dumps(hb_data), encoding="utf-8")


def test_heal_stale_in_progress_flips_to_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stale heartbeat → task flipped to PENDING and returned in healed list."""
    monkeypatch.chdir(tmp_path)
    task_id = "task_100"
    map_path = _write_map_with_task(tmp_path, task_id)
    _write_task_file(tmp_path, task_id)

    hb_request = WriteHeartbeatRequest(
        task_id=task_id,
        workspace=tmp_path,
        tool_count=5,
        dispatch_mode="claude_session",
    )
    write_heartbeat(hb_request)
    params = _BackdateParams(tmp_path, task_id, WORKER_HEARTBEAT_STALE_SECONDS + 10)
    _backdate_heartbeat(tmp_path, params)

    healed = heal_stale_in_progress(tmp_path)

    assert task_id in healed
    updated_map = map_path.read_text(encoding="utf-8")
    assert "PENDING" in updated_map
    assert f"[{task_id}_test.md]" in updated_map


def test_fresh_heartbeat_is_not_healed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fresh heartbeat → task stays IN_PROGRESS and not in healed list."""
    monkeypatch.chdir(tmp_path)
    task_id = "task_101"
    map_path = _write_map_with_task(tmp_path, task_id)
    _write_task_file(tmp_path, task_id)

    hb_request = WriteHeartbeatRequest(
        task_id=task_id,
        workspace=tmp_path,
        tool_count=5,
        dispatch_mode="claude_session",
    )
    write_heartbeat(hb_request)

    healed = heal_stale_in_progress(tmp_path)

    assert task_id not in healed
    updated_map = map_path.read_text(encoding="utf-8")
    assert "IN_PROGRESS" in updated_map
    assert f"[{task_id}_test.md]" in updated_map


def test_missing_heartbeat_is_healed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing heartbeat file → task flipped to PENDING and returned in healed list."""
    monkeypatch.chdir(tmp_path)
    task_id = "task_102"
    map_path = _write_map_with_task(tmp_path, task_id)
    _write_task_file(tmp_path, task_id)

    hb_dir = tmp_path / ".fsm-worker-hb"
    hb_dir.mkdir(parents=True, exist_ok=True)

    healed = heal_stale_in_progress(tmp_path)

    assert task_id in healed
    updated_map = map_path.read_text(encoding="utf-8")
    assert "PENDING" in updated_map
    assert f"[{task_id}_test.md]" in updated_map


def test_invalid_heartbeat_is_healed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A heartbeat file with invalid JSON should be treated as stale and healed."""
    monkeypatch.chdir(tmp_path)
    task_id = "task_999"
    _write_map_with_task(tmp_path, task_id)
    _write_task_file(tmp_path, task_id)
    hb_dir = tmp_path / ".fsm-worker-hb"
    hb_dir.mkdir(exist_ok=True)
    (hb_dir / "task_999.json").write_bytes(b"\xff\xfe not valid json")
    healed = heal_stale_in_progress(tmp_path)
    assert "task_999" in healed
