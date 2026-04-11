#!/usr/bin/env python3
"""PostToolUse Read hook: update agent_seen bookkeeping in the repo map."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.repo_map.models import AgentSeen, FileIndex, RepoMap
from src.repo_map.store import load_map, save_map

logger = logging.getLogger(__name__)

LAST_INDEX: int = -1

@dataclass
class PostReadEvent:
    """Parsed fields from a PostToolUse Read hook event."""

    file_path: str
    offset: int
    limit: Optional[int]
    outline_was_shown: bool
    project_root: str


@dataclass
class RangeRequest:
    """Parameters for resolving a line range from a read event."""

    offset: int
    limit: Optional[int]
    line_count: int


def _parse_event(raw: str) -> Optional[PostReadEvent]:
    """Parse stdin JSON into a PostReadEvent; return None on failure."""
    try:
        data = json.loads(raw)
        tool_input = data.get("tool_input", {})
        project_root = data.get("cwd", "")
        raw_limit = tool_input.get("limit")
        return PostReadEvent(
            file_path=tool_input.get("file_path", ""),
            offset=int(tool_input.get("offset") or 1),
            limit=int(raw_limit) if raw_limit is not None else None,
            outline_was_shown=bool(data.get("outline_was_shown", False)),
            project_root=project_root,
        )
    except Exception:
        logger.exception("Failed to parse PostToolUse Read event")
        return None


def _resolve_range(req: RangeRequest) -> Tuple[int, int]:
    """Compute inclusive (start, end) line range from offset and limit."""
    start = max(1, req.offset)
    if req.limit is None:
        return (start, req.line_count)
    end = min(req.line_count, start + req.limit - 1)
    return (start, end)


def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping inclusive (start, end) tuples into a minimal list."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged: List[Tuple[int, int]] = [sorted_ranges[0]]
    for current in sorted_ranges[1:]:
        prev_start, prev_end = merged[LAST_INDEX]
        cur_start, cur_end = current
        if cur_start <= prev_end + 1:
            merged[LAST_INDEX] = (prev_start, max(prev_end, cur_end))
        else:
            merged.append(current)
    return merged


def _apply_ranges(entry: FileIndex, event: PostReadEvent) -> None:
    """Append and merge the new read range into entry.agent_seen."""
    if entry.agent_seen is None:
        entry.agent_seen = AgentSeen()
    req = RangeRequest(offset=event.offset, limit=event.limit, line_count=entry.line_count)
    new_range = _resolve_range(req)
    entry.agent_seen.ranges_read.append(new_range)
    entry.agent_seen.ranges_read = _merge_ranges(entry.agent_seen.ranges_read)
    if event.outline_was_shown:
        entry.agent_seen.outline_shown = True


def _update_agent_seen(repo_map: RepoMap, event: PostReadEvent) -> None:
    """Locate entry in repo_map and update its agent_seen from event."""
    entry = repo_map.entries.get(str(Path(event.file_path).resolve()))
    if entry is None:
        return
    _apply_ranges(entry, event)


def main() -> None:
    """Parse stdin event, update agent_seen bookkeeping, save map."""
    raw = sys.stdin.read()
    event = _parse_event(raw)
    if event is None or not event.file_path or not event.project_root:
        sys.exit(0)
    try:
        repo_map = load_map(Path(event.project_root))
        _update_agent_seen(repo_map, event)
        save_map(repo_map)
    except Exception:
        logger.exception("post_read: failed to update map for %s", event.file_path)
    sys.exit(0)


if __name__ == "__main__":
    main()
