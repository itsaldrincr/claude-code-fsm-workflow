"""DAG wave analyzer: topological sort of task dependency graphs."""

from __future__ import annotations

import copy
from pathlib import Path

THREE_PARTS = 3


class DependencyCycleError(ValueError):
    """Raised when the task graph contains a cycle.

    The message lists every task_id participating in the cycle.
    """

    def __init__(self, cycle_members: list[str]) -> None:
        self.cycle_members = cycle_members
        super().__init__(f"Dependency cycle detected among: {', '.join(cycle_members)}")


def compute_waves(task_paths: list[Path]) -> list[list[str]]:
    """Return topologically-sorted waves of task IDs from frontmatter.

    Raises DependencyCycleError on cycle, ValueError on malformed frontmatter.
    """
    frontmatters = [parse_task_frontmatter(p) for p in task_paths]
    graph = _build_graph(frontmatters)
    return _kahn(graph)


def parse_task_frontmatter(task_path: Path) -> tuple[str, list[str]]:
    """Read task file, extract YAML frontmatter, return (id, depends)."""
    text = task_path.read_text()
    raw_id, raw_depends = _extract_frontmatter_fields(text)
    return raw_id.strip(), _parse_depends_value(raw_depends)


def _extract_frontmatter_fields(text: str) -> tuple[str, str]:
    """Extract raw id and depends strings from YAML frontmatter block."""
    parts = text.split("---")
    if len(parts) < THREE_PARTS:
        raise ValueError("No valid frontmatter delimiters found")
    block = parts[1]
    task_id = _find_field(block, "id:")
    depends = _find_field(block, "depends:")
    return task_id, depends


def _find_field(block: str, prefix: str) -> str:
    """Return the value string after prefix in block, or empty string."""
    for line in block.splitlines():
        if line.strip().startswith(prefix):
            return line.split(prefix, 1)[1]
    return ""


def _parse_depends_value(raw: str) -> list[str]:
    """Parse flow-style [a, b] or block-style dash list into list of IDs."""
    stripped = raw.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1]
        if not inner.strip():
            return []
        return [item.strip() for item in inner.split(",") if item.strip()]
    lines = [ln.strip().lstrip("- ").strip() for ln in stripped.splitlines() if ln.strip().startswith("-")]
    return [item for item in lines if item]


def _build_graph(frontmatters: list[tuple[str, list[str]]]) -> dict[str, set[str]]:
    """Build adjacency dict mapping each task_id to its dependencies.

    Raises ValueError if a dependency ID is not present in the frontmatters.
    """
    known_ids = {task_id for task_id, _ in frontmatters}
    graph: dict[str, set[str]] = {}
    for task_id, deps in frontmatters:
        for dep in deps:
            if dep not in known_ids:
                raise ValueError(
                    f"Task '{task_id}' depends on '{dep}', which is not in the provided task list"
                )
        graph.setdefault(task_id, set()).update(deps)
    return graph


def _kahn(graph: dict[str, set[str]]) -> list[list[str]]:
    """Run Kahn's algorithm; return waves or raise DependencyCycleError."""
    remaining = copy.deepcopy(graph)
    waves: list[list[str]] = []
    while True:
        zero_in = sorted(n for n, deps in remaining.items() if not deps)
        if not zero_in:
            break
        waves.append(zero_in)
        _remove_wave(remaining, zero_in)
    if remaining:
        raise DependencyCycleError(_find_cycle_members(graph, set(remaining)))
    return waves


def _remove_wave(remaining: dict[str, set[str]], wave: list[str]) -> None:
    """Remove completed wave nodes and update in-degrees of dependents."""
    for node in wave:
        del remaining[node]
    for deps in remaining.values():
        deps -= set(wave)


def _find_cycle_members(graph: dict[str, set[str]], remaining: set[str]) -> list[str]:
    """Return list of node IDs participating in a cycle within remaining."""
    subgraph = {n: graph.get(n, set()) & remaining for n in remaining}
    in_cycle = [node for node in remaining if _reaches_self(subgraph, node)]
    return in_cycle if in_cycle else list(remaining)


def _reaches_self(subgraph: dict[str, set[str]], start: str) -> bool:
    """Return True if start can reach itself via subgraph edges."""
    visited: set[str] = set()
    stack = list(subgraph.get(start, set()))
    while stack:
        node = stack.pop()
        if node == start:
            return True
        if node not in visited:
            visited.add(node)
            stack.extend(subgraph.get(node, set()) - visited)
    return False
