import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.fsm_core.map_io import (
    ReadStatusesRequest,
    StatusUpdateRequest,
    read_map_statuses,
    update_map_status,
)


@dataclass
class _FlipArgs:
    map_path: Path
    task_id: str
    status: str

MAP_CONTENT: str = """\
# MAP

## Active Tasks

### Wave 1
Project/
  src/engine/      [task_011_map_lock.md] ........ PENDING
  src/engine/      [task_012_trace.md] ........... PENDING
"""

ALL_STATUSES_MAP_CONTENT: str = """\
# MAP

## Active Tasks

  [task_001_a.md] ........ PENDING
  [task_002_b.md] ........ IN_PROGRESS
  [task_003_c.md] ........ DONE
  [task_004_d.md] ........ VERIFY
  [task_005_e.md] ........ REVIEW
  [task_006_f.md] ........ BLOCKED
  [task_007_g.md] ........ FAILED
  [task_008_h.md] ........ PARTIAL
  [task_009_i.md] ........ EXECUTING
"""


def _write_map(tmp_path: Path, content: str) -> Path:
    """Write synthetic MAP.md to tmp_path and return its path."""
    map_path = tmp_path / "MAP.md"
    map_path.write_text(content, encoding="utf-8")
    return map_path


def test_status_flip(tmp_path: Path) -> None:
    """Status flip rewrites the correct task's status token."""
    map_path = _write_map(tmp_path, MAP_CONTENT)
    request = StatusUpdateRequest(map_path, "task_011", "IN_PROGRESS")
    update_map_status(request)
    result = map_path.read_text(encoding="utf-8")
    assert "IN_PROGRESS" in result
    assert "[task_011_map_lock.md]" in result
    assert "task_012" in result
    lines = [ln for ln in result.splitlines() if "task_011" in ln]
    assert len(lines) == 1
    assert "IN_PROGRESS" in lines[0]
    pending_lines = [ln for ln in result.splitlines() if "task_012" in ln]
    assert "PENDING" in pending_lines[0]


def test_unknown_task_id_raises(tmp_path: Path) -> None:
    """ValueError is raised when task_id is not found in MAP.md."""
    map_path = _write_map(tmp_path, MAP_CONTENT)
    request = StatusUpdateRequest(map_path, "task_999", "DONE")
    with pytest.raises(ValueError, match="task_999"):
        update_map_status(request)


def test_missing_map_raises(tmp_path: Path) -> None:
    """FileNotFoundError is raised when map_path does not exist."""
    map_path = tmp_path / "nonexistent_MAP.md"
    request = StatusUpdateRequest(map_path, "task_011", "DONE")
    with pytest.raises(FileNotFoundError):
        update_map_status(request)


def test_invalid_status_raises() -> None:
    """ValueError is raised on construction with invalid new_status."""
    with pytest.raises(ValueError, match="INVALID"):
        StatusUpdateRequest(Path("/tmp/MAP.md"), "task_011", "INVALID")


def _flip_status(args: _FlipArgs, barrier: threading.Barrier) -> None:
    """Thread worker: wait at barrier then flip status."""
    barrier.wait()
    request = StatusUpdateRequest(args.map_path, args.task_id, args.status)
    update_map_status(request)


def test_concurrent_writes_no_corruption(tmp_path: Path) -> None:
    """Two concurrent update_map_status calls serialize without corruption."""
    map_path = _write_map(tmp_path, MAP_CONTENT)
    barrier = threading.Barrier(2)
    args1 = _FlipArgs(map_path=map_path, task_id="task_011", status="IN_PROGRESS")
    args2 = _FlipArgs(map_path=map_path, task_id="task_012", status="DONE")
    t1 = threading.Thread(target=_flip_status, args=(args1, barrier))
    t2 = threading.Thread(target=_flip_status, args=(args2, barrier))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    result = map_path.read_text(encoding="utf-8")
    assert "IN_PROGRESS" in result
    assert "DONE" in result
    assert "[task_011_map_lock.md]" in result
    assert "[task_012_trace.md]" in result


def test_read_map_statuses_returns_dict(tmp_path: Path) -> None:
    """read_map_statuses returns dict mapping task_id to status."""
    map_path = _write_map(tmp_path, MAP_CONTENT)
    request = ReadStatusesRequest(map_path)
    result = read_map_statuses(request)
    assert isinstance(result, dict)
    assert result["task_011"] == "PENDING"
    assert result["task_012"] == "PENDING"


def test_read_map_statuses_missing_file_raises(tmp_path: Path) -> None:
    """FileNotFoundError raised when map_path does not exist."""
    map_path = tmp_path / "nonexistent_MAP.md"
    request = ReadStatusesRequest(map_path)
    with pytest.raises(FileNotFoundError):
        read_map_statuses(request)


def test_read_map_statuses_all_9_statuses(tmp_path: Path) -> None:
    """read_map_statuses handles all 9 valid status values."""
    map_path = _write_map(tmp_path, ALL_STATUSES_MAP_CONTENT)
    request = ReadStatusesRequest(map_path)
    result = read_map_statuses(request)
    expected_pairs: list[tuple[str, str]] = [
        ("task_001", "PENDING"),
        ("task_002", "IN_PROGRESS"),
        ("task_003", "DONE"),
        ("task_004", "VERIFY"),
        ("task_005", "REVIEW"),
        ("task_006", "BLOCKED"),
        ("task_007", "FAILED"),
        ("task_008", "PARTIAL"),
        ("task_009", "EXECUTING"),
    ]
    assert len(result) == 9
    for task_id, expected_status in expected_pairs:
        assert result[task_id] == expected_status


def test_status_update_accepts_all_9_statuses() -> None:
    """StatusUpdateRequest accepts all 9 valid status values."""
    map_path = Path("/tmp/MAP.md")
    statuses = [
        "PENDING",
        "IN_PROGRESS",
        "DONE",
        "VERIFY",
        "REVIEW",
        "BLOCKED",
        "FAILED",
        "PARTIAL",
        "EXECUTING",
    ]
    for status in statuses:
        request = StatusUpdateRequest(map_path, "task_001", status)
        assert request.new_status == status


def test_valid_statuses_contains_9_states() -> None:
    """VALID_STATUSES contains exactly the 9 required state values."""
    from src.fsm_core.map_io import VALID_STATUSES

    expected_statuses = {
        "PENDING",
        "IN_PROGRESS",
        "DONE",
        "VERIFY",
        "REVIEW",
        "BLOCKED",
        "FAILED",
        "PARTIAL",
        "EXECUTING",
    }
    assert VALID_STATUSES == frozenset(expected_statuses)
    assert len(VALID_STATUSES) == 9


def test_read_map_statuses_empty_map_returns_empty_dict(tmp_path: Path) -> None:
    """read_map_statuses returns empty dict when MAP.md has no task entries."""
    empty_map_content = """\
# MAP

## Active Tasks

## Completed
— none —
"""
    map_path = _write_map(tmp_path, empty_map_content)
    request = ReadStatusesRequest(map_path)
    result = read_map_statuses(request)
    assert result == {}
    assert isinstance(result, dict)


def test_read_map_statuses_skips_invalid_status(tmp_path: Path) -> None:
    """read_map_statuses excludes entries with unrecognized status values."""
    content = """\
# MAP

## Active Tasks

  [task_001_a.md] ........ PENDING
  [task_002_b.md] ........ BOGUS
  [task_003_c.md] ........ DONE
"""
    map_path = _write_map(tmp_path, content)
    request = ReadStatusesRequest(map_path)
    result = read_map_statuses(request)
    assert "task_001" in result
    assert "task_002" not in result
    assert "task_003" in result
