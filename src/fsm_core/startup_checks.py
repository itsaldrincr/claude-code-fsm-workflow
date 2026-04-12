"""Startup validation checks for orchestrator execution."""

from dataclasses import dataclass
from pathlib import Path
import re

from src import config
from src.fsm_core.frontmatter import parse_frontmatter
from src.fsm_core.map_io import ReadStatusesRequest, read_map_statuses

_SUPPORTED_MODES: frozenset[str] = frozenset({"claude_session"})
_STATE_LINE_RE: re.Pattern[str] = re.compile(r"^state:\s*.+$", re.MULTILINE)


@dataclass(frozen=True)
class StateDrift:
    """Represents a MAP.md status and task frontmatter state mismatch."""

    task_id: str
    map_status: str
    task_state: str
    task_path: Path


def resolve_dispatch_mode(mode: str | None) -> str:
    """Normalize dispatch mode and validate supported values."""
    raw = (mode or config.DISPATCH_MODE).strip()
    normalized = raw
    if normalized not in _SUPPORTED_MODES:
        allowed = ", ".join(sorted(_SUPPORTED_MODES))
        raise ValueError(f"Unsupported dispatch mode {raw!r}. Allowed: {allowed}")
    return normalized


def _find_task_file(workspace: Path, task_id: str) -> Path | None:
    """Return first task file matching task_id in workspace."""
    matches = sorted(workspace.glob(f"{task_id}_*.md"))
    return matches[0] if matches else None


def _rewrite_state_line(content: str, new_state: str) -> str:
    """Return content with frontmatter state line replaced."""
    lines = content.splitlines()
    first = -1
    second = -1
    for idx, line in enumerate(lines):
        if line.strip() != "---":
            continue
        if first < 0:
            first = idx
            continue
        second = idx
        break
    if first < 0 or second < 0:
        return content
    block = "\n".join(lines[first + 1:second])
    replaced = _STATE_LINE_RE.sub(f"state: {new_state}", block, count=1)
    if replaced == block:
        return content
    updated = lines[: first + 1] + replaced.splitlines() + lines[second:]
    return "\n".join(updated) + ("\n" if content.endswith("\n") else "")


def find_state_drifts(workspace: Path, map_path: Path) -> list[StateDrift]:
    """Compare MAP statuses vs task frontmatter states and return mismatches."""
    statuses = read_map_statuses(ReadStatusesRequest(map_path=map_path))
    drifts: list[StateDrift] = []
    for task_id, map_status in statuses.items():
        task_path = _find_task_file(workspace, task_id)
        if task_path is None:
            continue
        content = task_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm.state == map_status:
            continue
        drifts.append(
            StateDrift(
                task_id=task_id,
                map_status=map_status,
                task_state=fm.state,
                task_path=task_path,
            )
        )
    return drifts


def sync_task_states_to_map(drifts: list[StateDrift]) -> int:
    """Mutate task files so frontmatter state matches MAP status for each drift."""
    changed = 0
    for drift in drifts:
        content = drift.task_path.read_text(encoding="utf-8")
        updated = _rewrite_state_line(content, drift.map_status)
        if updated == content:
            continue
        drift.task_path.write_text(updated, encoding="utf-8")
        changed += 1
    return changed
