"""Tests for src/fsm_core/dag_waves.py."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.fsm_core.dag_waves import DependencyCycleError, compute_waves

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@dataclass
class _WaveGroups:
    wave0: list[str]
    wave1: list[str]
    wave2: list[str]
    wave3: list[str]


def test_simple_three_node_dag() -> None:
    """AC3.1: 3-node linear DAG yields [[task_a], [task_b], [task_c]]."""
    paths = [
        FIXTURES_DIR / "sample_task_a.md",
        FIXTURES_DIR / "sample_task_b.md",
        FIXTURES_DIR / "sample_task_c.md",
    ]
    result = compute_waves(paths)
    assert result == [["task_a"], ["task_b"], ["task_c"]]


def test_cycle_raises_with_members() -> None:
    """AC3.2: 3-node cycle raises DependencyCycleError naming all members."""
    paths = [
        FIXTURES_DIR / "sample_task_cycle_a.md",
        FIXTURES_DIR / "sample_task_cycle_b.md",
        FIXTURES_DIR / "sample_task_cycle_c.md",
    ]
    with pytest.raises(DependencyCycleError) as exc_info:
        compute_waves(paths)
    members = exc_info.value.cycle_members
    assert "task_cycle_a" in members
    assert "task_cycle_b" in members
    assert "task_cycle_c" in members


def test_twelve_task_four_wave(tmp_path: Path) -> None:
    """AC3.3: 12 tasks in 4 waves — correct partition, union=all 12, no overlap."""
    task_files = _create_twelve_task_fixtures(tmp_path)
    result = compute_waves(task_files)
    assert len(result) == 4
    _assert_no_overlap(result)
    _assert_union_covers_all(result)


def _create_twelve_task_fixtures(tmp_path: Path) -> list[Path]:
    """Create 12 task fixture files forming 4 distinct waves of 3 tasks each."""
    wave0 = ["t1", "t2", "t3"]
    wave1 = ["t4", "t5", "t6"]
    wave2 = ["t7", "t8", "t9"]
    wave3 = ["t10", "t11", "t12"]
    groups = _WaveGroups(wave0=wave0, wave1=wave1, wave2=wave2, wave3=wave3)
    definitions = _build_task_definitions(groups)
    return _write_task_files(tmp_path, definitions)


def _build_task_definitions(
    groups: _WaveGroups,
) -> list[tuple[str, list[str]]]:
    """Return (id, deps) pairs for each of the 12 tasks."""
    entries: list[tuple[str, list[str]]] = []
    entries.extend((tid, []) for tid in groups.wave0)
    entries.extend((tid, groups.wave0) for tid in groups.wave1)
    entries.extend((tid, groups.wave1) for tid in groups.wave2)
    entries.extend((tid, groups.wave2) for tid in groups.wave3)
    return entries


def _write_task_files(
    tmp_path: Path,
    definitions: list[tuple[str, list[str]]],
) -> list[Path]:
    """Write frontmatter fixture files for each (id, deps) definition."""
    files: list[Path] = []
    for task_id, deps in definitions:
        dep_str = "[" + ", ".join(deps) + "]"
        content = f"---\nid: {task_id}\ndepends: {dep_str}\n---\n"
        fpath = tmp_path / f"{task_id}.md"
        fpath.write_text(content)
        files.append(fpath)
    return files


def _assert_no_overlap(waves: list[list[str]]) -> None:
    """Assert no task_id appears in more than one wave."""
    seen: set[str] = set()
    for wave in waves:
        for task_id in wave:
            assert task_id not in seen, f"{task_id} appears in multiple waves"
            seen.add(task_id)


def _assert_union_covers_all(waves: list[list[str]]) -> None:
    """Assert the union of all waves equals the expected 12 task IDs."""
    expected = {f"t{i}" for i in range(1, 13)}
    actual = {task_id for wave in waves for task_id in wave}
    assert actual == expected
