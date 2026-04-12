import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from src.fsm_core.map_lock import map_lock


@dataclass(frozen=True)
class _RewriteParams:
    task_id: str
    new_status: str

logger = logging.getLogger(__name__)

VALID_STATUSES: frozenset[str] = frozenset(
    {"PENDING", "IN_PROGRESS", "DONE", "VERIFY", "REVIEW", "BLOCKED", "FAILED", "PARTIAL", "EXECUTING"}
)
STATUS_PATTERN_TEMPLATE: str = r'(\[' + '{task_id}' + r'[^\]]*\])\s*(\.+)\s*(\w+)'


@dataclass(frozen=True)
class StatusUpdateRequest:
    """Request to flip a task's status in MAP.md."""

    map_path: Path
    task_id: str
    new_status: str

    def __post_init__(self) -> None:
        """Validate new_status is one of the allowed status values."""
        if self.new_status not in VALID_STATUSES:
            raise ValueError(
                f"new_status {self.new_status!r} not in {VALID_STATUSES}"
            )


@dataclass(frozen=True)
class ReadStatusesRequest:
    """Request to read task statuses from MAP.md."""

    map_path: Path


def _rewrite_status_line(content: str, params: _RewriteParams) -> str:
    """Replace the trailing status token on the line containing [task_id...]."""
    pattern = STATUS_PATTERN_TEMPLATE.replace("{task_id}", re.escape(params.task_id))
    replacement = r'\1 \2 ' + params.new_status
    result, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise ValueError(f"task_id {params.task_id!r} not found in MAP.md content")
    return result


def update_map_status(request: StatusUpdateRequest) -> None:
    """Flip a task's status field in MAP.md under map_lock.

    Raises:
        FileNotFoundError: MAP.md does not exist.
        ValueError: task_id not found in MAP.md.
        LockTimeoutError: propagated from map_lock.
    """
    if not request.map_path.exists():
        raise FileNotFoundError(f"MAP.md not found at {request.map_path}")
    tmp_path = Path(str(request.map_path) + ".tmp")
    with map_lock(request.map_path):
        content = request.map_path.read_text(encoding="utf-8")
        params = _RewriteParams(task_id=request.task_id, new_status=request.new_status)
        updated = _rewrite_status_line(content, params)
        tmp_path.write_text(updated, encoding="utf-8")
        os.replace(tmp_path, request.map_path)
    logger.debug("Updated %s → %s in %s", request.task_id, request.new_status, request.map_path)


def _extract_task_id(filename: str) -> str | None:
    """Extract task_id from filename like 'task_801a_foo.md' -> 'task_801a'."""
    match = re.match(r'^(task_\d+[a-z]?)', filename.replace('.md', ''))
    return match.group(1) if match else None


def _parse_status_line(filename: str, status: str) -> tuple[str, str] | None:
    """Parse one status line. Return (task_id, status) or None if invalid."""
    task_id = _extract_task_id(filename)
    if not task_id:
        return None
    if status not in VALID_STATUSES:
        logger.warning("Unrecognized status %r for %s — skipping", status, task_id)
        return None
    return task_id, status


def read_map_statuses(request: ReadStatusesRequest) -> dict[str, str]:
    """Parse MAP.md under lock and return {task_id: status} dict."""
    if not request.map_path.exists():
        raise FileNotFoundError(f"MAP.md not found at {request.map_path}")
    statuses: dict[str, str] = {}
    with map_lock(request.map_path):
        content = request.map_path.read_text(encoding="utf-8")
        pattern = r'\[([^\]]*\.md)\]\s*(\.+)\s*(\w+)'
        for match in re.finditer(pattern, content):
            filename = match.group(1)
            status = match.group(3)
            result = _parse_status_line(filename, status)
            if result:
                task_id, valid_status = result
                statuses[task_id] = valid_status
    return statuses
