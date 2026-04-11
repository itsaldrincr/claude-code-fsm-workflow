#!/usr/bin/env python3
"""PostToolUse Edit/Write/MultiEdit hook: invalidate repo map entries."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.repo_map.models import RepoMap
from src.repo_map.store import load_map, save_map

logger = logging.getLogger(__name__)


def _collect_paths(data: dict) -> List[Path]:
    """Extract file paths from Edit, Write, or MultiEdit tool_input."""
    tool_input = data.get("tool_input", {})
    tool_name = data.get("tool_name", "")
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        return [Path(e["file_path"]) for e in edits if "file_path" in e]
    single = tool_input.get("file_path", "")
    if single:
        return [Path(single)]
    return []


def _parse_event(raw: str) -> Optional[Tuple[str, List[Path]]]:
    """Parse stdin JSON; return (project_root, list[Path]) or None on failure."""
    try:
        data = json.loads(raw)
        project_root = data.get("cwd", "")
        paths = _collect_paths(data)
        return (project_root, paths)
    except Exception:
        logger.exception("Failed to parse PostToolUse Edit/Write/MultiEdit event")
        return None


def _invalidate_one(repo_map: RepoMap, path: Path) -> None:
    """Remove the entry for path from repo_map.entries if present."""
    key = str(path.resolve())
    if key in repo_map.entries:
        del repo_map.entries[key]


def _save(repo_map: RepoMap, paths: List[Path]) -> None:
    """Invalidate all paths then save the map."""
    for path in paths:
        _invalidate_one(repo_map, path)
    save_map(repo_map)


def main() -> None:
    """Parse stdin event, invalidate affected entries, save map."""
    raw = sys.stdin.read()
    result = _parse_event(raw)
    if result is None:
        sys.exit(0)
    project_root, paths = result
    if not project_root or not paths:
        sys.exit(0)
    try:
        repo_map = load_map(Path(project_root))
        _save(repo_map, paths)
    except Exception:
        logger.exception("post_edit: failed to invalidate entries for %s", paths)
    sys.exit(0)


if __name__ == "__main__":
    main()
