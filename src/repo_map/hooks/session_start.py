#!/usr/bin/env python3
"""SessionStart hook: emit orientation summary and clear agent_seen on all entries."""

from __future__ import annotations

import collections
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.repo_map.models import AgentSeen, FileIndex, RepoMap
from src.repo_map.store import load_map, save_map

logger = logging.getLogger(__name__)

TOP_N_DIRS = 5
TOP_N_HUBS = 5


@dataclass
class ReverseQuery:
    """Parameters for reverse import degree lookup."""

    candidate_path: str
    tokens: List[str]


@dataclass
class SummaryRequest:
    """Holds data needed to format the orientation summary."""

    file_count: int
    top_dirs: List[str]
    hub_files: List[str]


def _top_directories(entries: Dict[str, FileIndex]) -> List[str]:
    """Return the top TOP_N_DIRS directories by file count."""
    counter: collections.Counter = collections.Counter()
    for path in entries:
        counter[str(Path(path).parent)] += 1
    return [d for d, _ in counter.most_common(TOP_N_DIRS)]


def _make_match_tokens(file_path: str) -> List[str]:
    """Return basename-without-ext and dotted-path tokens for a file path."""
    p = Path(file_path)
    stem = p.stem
    dotted = re.sub(r"[/\\]", ".", str(p)).lstrip(".")
    for ext in (".py", ".ts", ".tsx", ".js", ".jsx"):
        if dotted.endswith(ext):
            dotted = dotted[: -len(ext)]
            break
    return [stem, dotted]


def _reverse_degree(query: ReverseQuery, entries: Dict[str, FileIndex]) -> int:
    """Count how many other entries import the candidate via any of its tokens."""
    count = 0
    for path, entry in entries.items():
        if path == query.candidate_path:
            continue
        for imp_str in entry.imports:
            if any(re.search(r"\b" + re.escape(tok) + r"\b", imp_str) for tok in query.tokens):
                count += 1
                break
    return count


def _hub_files(entries: Dict[str, FileIndex]) -> List[str]:
    """Return the top TOP_N_HUBS files by reverse import degree."""
    counter: collections.Counter = collections.Counter()
    for path in entries:
        tokens = _make_match_tokens(path)
        counter[path] = _reverse_degree(ReverseQuery(candidate_path=path, tokens=tokens), entries)
    return [f for f, _ in counter.most_common(TOP_N_HUBS) if counter[f] > 0]


def _format_summary(request: SummaryRequest) -> str:
    """Format the orientation summary string."""
    dirs_str = ", ".join(request.top_dirs) if request.top_dirs else "(none)"
    hubs_str = ", ".join(request.hub_files) if request.hub_files else "(none)"
    return (
        f"## Repo map ({request.file_count} files indexed)\n\n"
        f"Top directories: {dirs_str}\n\n"
        f"Hub files: {hubs_str}"
    )


def _build_summary(repo_map: RepoMap) -> str:
    """Build the full orientation summary string from a RepoMap."""
    entries = repo_map.entries
    top_dirs = _top_directories(entries)
    hub_files = _hub_files(entries)
    request = SummaryRequest(
        file_count=len(entries),
        top_dirs=top_dirs,
        hub_files=hub_files,
    )
    return _format_summary(request)


def _clear_agent_seen(repo_map: RepoMap) -> None:
    """Reset agent_seen on every entry to a blank AgentSeen."""
    for entry in repo_map.entries.values():
        entry.agent_seen = AgentSeen(ranges_read=[], outline_shown=False)


def _parse_project_root(raw: dict) -> Path:
    """Extract project_root from hook payload, falling back to cwd."""
    root = raw.get("project_root") or raw.get("cwd")
    return Path(root) if root else Path.cwd()


def main() -> None:
    """Parse stdin, emit orientation summary to stdout, clear agent_seen, save."""
    raw = json.loads(sys.stdin.read() or "{}")
    project_root = _parse_project_root(raw)
    repo_map = load_map(project_root)
    if not repo_map.entries:
        sys.exit(0)
    summary = _build_summary(repo_map)
    sys.stdout.write(summary + "\n")
    _clear_agent_seen(repo_map)
    save_map(repo_map)


if __name__ == "__main__":
    main()
