import logging
from dataclasses import dataclass
from pathlib import Path

from src.fsm_core.frontmatter import parse_frontmatter
from src.fsm_core.map_io import ReadStatusesRequest, read_map_statuses

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskInfo:
    """Information about a task from MAP.md and its frontmatter."""

    task_id: str
    status: str
    dispatch_role: str
    depends: list[str]
    wave: int
    requires_user_confirmation: bool
    task_path: str


@dataclass(frozen=True)
class ReadTasksRequest:
    """Request to read task dispatch info from workspace and MAP.md."""

    workspace: Path
    map_path: Path


def _find_task_file(workspace: Path, task_id: str) -> Path | None:
    """Glob for {task_id}_*.md in workspace and return first match or None."""
    pattern = f"{task_id}_*.md"
    matches = list(workspace.glob(pattern))
    if len(matches) > 1:
        logger.warning("Multiple task files for %s: %s", task_id, [str(m) for m in matches])
    return matches[0] if matches else None


@dataclass(frozen=True)
class _BuildTaskInfoRequest:
    """Internal request for building TaskInfo from a task file."""

    task_id: str
    status: str
    task_path: Path


@dataclass(frozen=True)
class _ProcessTaskStatusRequest:
    """Internal request for processing a single task status."""

    workspace: Path
    task_id: str
    status: str


def _build_task_info(request: _BuildTaskInfoRequest) -> TaskInfo | None:
    """Parse task file and build TaskInfo, or return None if parsing fails."""
    try:
        content = request.task_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        return TaskInfo(
            task_id=request.task_id,
            status=request.status,
            dispatch_role=fm.dispatch,
            depends=fm.depends,
            wave=fm.wave,
            requires_user_confirmation=fm.requires_user_confirmation,
            task_path=str(request.task_path),
        )
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", request.task_path, exc)
        return None


def _process_task_status(request: _ProcessTaskStatusRequest) -> TaskInfo | None:
    """Load and build TaskInfo for a single task, or return None if not found/invalid."""
    task_path = _find_task_file(request.workspace, request.task_id)
    if not task_path:
        logger.warning("Task file not found for %s", request.task_id)
        return None
    build_request = _BuildTaskInfoRequest(request.task_id, request.status, task_path)
    return _build_task_info(build_request)


def read_task_dispatch_info(request: ReadTasksRequest) -> list[TaskInfo]:
    """Read task dispatch info by combining MAP.md statuses and task file frontmatter.

    For each task in MAP.md, loads the task file frontmatter and returns TaskInfo.
    Logs a warning and skips any task file not found on disk.
    """
    map_request = ReadStatusesRequest(map_path=request.map_path)
    statuses = read_map_statuses(map_request)

    tasks: list[TaskInfo] = []
    for task_id, status in statuses.items():
        process_request = _ProcessTaskStatusRequest(request.workspace, task_id, status)
        info = _process_task_status(process_request)
        if info:
            tasks.append(info)

    return tasks
