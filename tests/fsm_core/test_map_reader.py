import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.fsm_core.map_reader import (
    ReadTasksRequest,
    TaskInfo,
    read_task_dispatch_info,
)


SYNTHETIC_MAP_CONTENT: str = """\
# MAP

## Active Tasks

### Wave 1
  [task_801_model_registry.md] ........ PENDING
  [task_802_types.md] ................ PENDING

### Wave 2
  [task_803_composites.md] ........... PENDING  depends: 801, 802
"""

SYNTHETIC_TASK_801: str = """\
---
id: task_801
name: model_registry
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: 68428a
created: 2026-04-10
---

## Files
Creates:
  src/engine/model-registry.ts

## Program
1. Create model registry module

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] All tests pass
"""

SYNTHETIC_TASK_802: str = """\
---
id: task_802
name: message_types
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: abc123
created: 2026-04-10
---

## Files
Creates:
  src/types/messages.ts

## Program
1. Create message types module

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] All tests pass
"""

SYNTHETIC_TASK_803: str = """\
---
id: task_803
name: composites
state: PENDING
step: 0 of 1
depends: [task_801, task_802]
wave: 2
dispatch: fsm-integrator
checkpoint: def456
created: 2026-04-10
---

## Files
Creates:
  src/composites/index.ts

## Program
1. Create composites module

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] All tests pass
"""

EMPTY_MAP_CONTENT: str = """\
# MAP

## Active Tasks

## Completed
— none —
"""


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Set up temp workspace with MAP.md and synthetic task files."""
    map_path = tmp_path / "MAP.md"
    map_path.write_text(SYNTHETIC_MAP_CONTENT, encoding="utf-8")

    (tmp_path / "task_801_model_registry.md").write_text(
        SYNTHETIC_TASK_801, encoding="utf-8"
    )
    (tmp_path / "task_802_message_types.md").write_text(
        SYNTHETIC_TASK_802, encoding="utf-8"
    )
    (tmp_path / "task_803_composites.md").write_text(SYNTHETIC_TASK_803, encoding="utf-8")

    return tmp_path, map_path


def test_read_task_dispatch_info_populates_task_info(tmp_path: Path) -> None:
    """TaskInfo is correctly populated from MAP.md and task file frontmatter."""
    workspace, map_path = _setup_workspace(tmp_path)
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    assert len(result) == 3
    task_ids = [t.task_id for t in result]
    assert "task_801" in task_ids
    assert "task_802" in task_ids
    assert "task_803" in task_ids

    task_801 = next(t for t in result if t.task_id == "task_801")
    assert task_801.status == "PENDING"
    assert task_801.dispatch_role == "fsm-executor"
    assert task_801.depends == []
    assert task_801.wave == 1


def test_read_task_dispatch_info_includes_task_path(tmp_path: Path) -> None:
    """TaskInfo.task_path points to the actual task file."""
    workspace, map_path = _setup_workspace(tmp_path)
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    task_801 = next(t for t in result if t.task_id == "task_801")
    assert task_801.task_path.endswith("task_801_model_registry.md")
    assert Path(task_801.task_path).exists()


def test_read_task_dispatch_info_empty_map_returns_empty_list(tmp_path: Path) -> None:
    """read_task_dispatch_info returns empty list when MAP.md has no tasks."""
    workspace = tmp_path
    map_path = tmp_path / "MAP.md"
    map_path.write_text(EMPTY_MAP_CONTENT, encoding="utf-8")
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    assert result == []
    assert isinstance(result, list)


def test_read_task_dispatch_info_skips_missing_task_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing task file is logged at warning level and skipped (not crash)."""
    workspace = tmp_path
    map_path = tmp_path / "MAP.md"
    map_path.write_text(SYNTHETIC_MAP_CONTENT, encoding="utf-8")

    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    with caplog.at_level("WARNING"):
        result = read_task_dispatch_info(request)

    assert len(result) == 0
    assert "Task file not found for task_801" in caplog.text


def test_read_task_dispatch_info_handles_malformed_task_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Malformed task file is logged at warning level and skipped."""
    workspace = tmp_path
    map_path = tmp_path / "MAP.md"
    map_path.write_text(SYNTHETIC_MAP_CONTENT, encoding="utf-8")

    (tmp_path / "task_801_malformed.md").write_text("no frontmatter", encoding="utf-8")

    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    with caplog.at_level("WARNING"):
        result = read_task_dispatch_info(request)

    assert len(result) == 0
    assert "Failed to parse" in caplog.text


def test_read_task_dispatch_info_uses_read_map_statuses(tmp_path: Path) -> None:
    """read_task_dispatch_info calls read_map_statuses from map_io."""
    workspace, map_path = _setup_workspace(tmp_path)
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    statuses = [t.status for t in result]
    assert all(s == "PENDING" for s in statuses)


def test_read_task_dispatch_info_includes_dependencies(tmp_path: Path) -> None:
    """read_task_dispatch_info correctly reads task dependencies."""
    workspace, map_path = _setup_workspace(tmp_path)
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    task_803 = next(t for t in result if t.task_id == "task_803")
    assert task_803.depends == ["task_801", "task_802"]


def test_read_task_dispatch_info_multiple_waves(tmp_path: Path) -> None:
    """read_task_dispatch_info correctly reads wave numbers."""
    workspace, map_path = _setup_workspace(tmp_path)
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)

    result = read_task_dispatch_info(request)

    waves = {t.task_id: t.wave for t in result}
    assert waves["task_801"] == 1
    assert waves["task_802"] == 1
    assert waves["task_803"] == 2


def test_task_info_is_frozen() -> None:
    """TaskInfo dataclass is frozen (immutable)."""
    info = TaskInfo(
        task_id="test",
        status="PENDING",
        dispatch_role="fsm-executor",
        depends=[],
        wave=1,
        task_path="/tmp/test.md",
    )
    with pytest.raises(AttributeError):
        info.task_id = "modified"


def test_read_tasks_request_is_frozen() -> None:
    """ReadTasksRequest dataclass is frozen (immutable)."""
    req = ReadTasksRequest(workspace=Path("/tmp"), map_path=Path("/tmp/MAP.md"))
    with pytest.raises(AttributeError):
        req.workspace = Path("/other")
