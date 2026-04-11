#!/usr/bin/env python3
"""Stop hook: clear agent_seen on all entries and drop entries for missing files."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.repo_map.models import AgentSeen, RepoMap
from src.repo_map.store import load_map, save_map

logger = logging.getLogger(__name__)


def _parse_project_root(raw: dict) -> Path:
    """Extract project_root from hook payload, falling back to cwd."""
    root = raw.get("project_root") or raw.get("cwd")
    return Path(root) if root else Path.cwd()


def _collect_missing_keys(repo_map: RepoMap) -> List[str]:
    """Return list of entry keys whose paths no longer exist on disk."""
    return [key for key in repo_map.entries if not Path(key).exists()]


def _compact_and_clear(repo_map: RepoMap) -> None:
    """Remove missing-file entries and reset agent_seen on remaining entries."""
    missing_keys = _collect_missing_keys(repo_map)
    for key in missing_keys:
        del repo_map.entries[key]
        logger.debug("Dropped missing-file entry: %s", key)
    for entry in repo_map.entries.values():
        entry.agent_seen = AgentSeen(ranges_read=[], outline_shown=False)


def main() -> None:
    """Parse stdin, compact the map, clear agent_seen, save."""
    raw = json.loads(sys.stdin.read() or "{}")
    project_root = _parse_project_root(raw)
    repo_map = load_map(project_root)
    if not repo_map.entries:
        sys.exit(0)
    _compact_and_clear(repo_map)
    save_map(repo_map)


if __name__ == "__main__":
    main()
