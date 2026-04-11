"""Unit tests for scripts/atomize_task.py."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.atomize_task import (
    MapLineConfig,
    MapRewriteConfig,
    SubtaskConfig,
    _build_active_task_line,
    _build_file_directory_block,
    _extract_directory_from_parent_header,
    _extract_line_prefix,
    atomize_task,
    build_subtask,
    generate_subtask_id,
    parse_program_steps,
    parse_sections,
    rewrite_map_dependencies,
)
from src.fsm_core.frontmatter import parse_frontmatter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_task_3step.md"
EXPECTED_ID = "task_801"
EXPECTED_NAME = "sample_feature"
EXPECTED_WAVE = 2
EXPECTED_DEPENDS = ["task_800"]
EXPECTED_STEP_COUNT = 3
STEP_INDEX_THIRD = 2


def _read_fixture() -> str:
    """Read the 3-step fixture file."""
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _make_subtask_config(index: int, content: str) -> SubtaskConfig:
    """Build a SubtaskConfig for the given step index from fixture content."""
    frontmatter = parse_frontmatter(content)
    steps = parse_program_steps(content)
    sections = parse_sections(content)
    return SubtaskConfig(
        parent_frontmatter=frontmatter,
        step=steps[index],
        index=index,
        total_steps=len(steps),
        parent_sections=sections,
        nonce="aabbcc",
    )


def _make_single_step_content() -> str:
    """Build single-step task content for testing passthrough behavior."""
    return (
        "---\n"
        "id: task_802\n"
        "name: single_step_task\n"
        "state: PENDING\n"
        "step: 0 of 1\n"
        "depends: []\n"
        "wave: 1\n"
        "dispatch: fsm-executor\n"
        "checkpoint: 112233\n"
        "created: 2026-04-10\n"
        "---\n\n"
        "## Files\nCreates:\n  src/foo.py\n\n"
        "## Program\n"
        "1. Create `src/foo.py` — define Foo class.\n\n"
        "## Registers\n— empty —\n\n"
        "## Acceptance Criteria\n- [ ] src/foo.py exists\n"
    )


class TestParseFrontmatter(unittest.TestCase):
    """Verify YAML frontmatter fields extracted from fixture."""

    def test_parse_frontmatter(self) -> None:
        content = _read_fixture()
        fm = parse_frontmatter(content)
        self.assertEqual(fm.id, EXPECTED_ID)
        self.assertEqual(fm.name, EXPECTED_NAME)
        self.assertEqual(fm.state, "PENDING")
        self.assertEqual(fm.step, "0 of 3")
        self.assertEqual(fm.depends, EXPECTED_DEPENDS)
        self.assertEqual(fm.wave, EXPECTED_WAVE)
        self.assertEqual(fm.dispatch, "fsm-executor")
        self.assertEqual(fm.checkpoint, "abc123")
        self.assertEqual(fm.created, "2026-04-10")


class TestParseProgramSteps(unittest.TestCase):
    """Verify numbered steps extracted from fixture."""

    def test_parse_program_steps(self) -> None:
        content = _read_fixture()
        steps = parse_program_steps(content)
        self.assertEqual(len(steps), EXPECTED_STEP_COUNT)
        self.assertEqual(steps[0].number, 1)
        self.assertEqual(steps[1].number, 2)
        self.assertEqual(steps[STEP_INDEX_THIRD].number, 3)
        for step in steps:
            self.assertTrue(len(step.text) > 0, f"Step {step.number} text is empty")


class TestGenerateSubtaskIds(unittest.TestCase):
    """Verify letter-suffix ID generation for 3-step parent."""

    def test_generate_subtask_ids(self) -> None:
        parent_id = EXPECTED_ID
        generated = [generate_subtask_id(parent_id, i) for i in range(EXPECTED_STEP_COUNT)]
        self.assertEqual(generated[0], "task_801a")
        self.assertEqual(generated[1], "task_801b")
        self.assertEqual(generated[2], "task_801c")


class TestSubtaskDependencies(unittest.TestCase):
    """Verify dependency chain for atomized sub-tasks."""

    def test_subtask_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_copy = Path(tmpdir) / "task_801_sample_feature.md"
            fixture_copy.write_text(_read_fixture(), encoding="utf-8")
            created = atomize_task(str(fixture_copy))
            self.assertEqual(len(created), EXPECTED_STEP_COUNT)
            first = parse_frontmatter(Path(created[0]).read_text(encoding="utf-8"))
            self.assertEqual(first.depends, EXPECTED_DEPENDS)
            second = parse_frontmatter(Path(created[1]).read_text(encoding="utf-8"))
            self.assertEqual(second.depends, ["task_801a"])
            third = parse_frontmatter(Path(created[2]).read_text(encoding="utf-8"))
            self.assertEqual(third.depends, ["task_801b"])


class TestSubtaskFilesSection(unittest.TestCase):
    """Verify each sub-task carries the full parent Files section."""

    def test_subtask_files_section(self) -> None:
        content = _read_fixture()
        parent_sections = parse_sections(content)
        parent_files = parent_sections.get("Files", "")
        for i in range(EXPECTED_STEP_COUNT):
            cfg = _make_subtask_config(i, content)
            subtask_content = build_subtask(cfg)
            self.assertIn(parent_files, subtask_content)


class TestSubtaskNonces(unittest.TestCase):
    """Verify each sub-task has a unique 6-char hex checkpoint nonce."""

    def test_subtask_nonces(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture_copy = Path(tmpdir) / "task_801_sample_feature.md"
            fixture_copy.write_text(_read_fixture(), encoding="utf-8")
            created = atomize_task(str(fixture_copy))
            nonces = []
            for path in created:
                fm = parse_frontmatter(Path(path).read_text(encoding="utf-8"))
                self.assertRegex(fm.checkpoint, r"^[0-9a-f]{6}$")
                nonces.append(fm.checkpoint)
            self.assertEqual(len(nonces), len(set(nonces)), "Nonces must be unique")


class TestMapRewrite(unittest.TestCase):
    """Verify MAP.md dependency rewrite replaces parent with last sub-task."""

    def test_map_rewrite(self) -> None:
        map_content = (
            "# MAP\n\n"
            "## Active Tasks\n\n"
            "Project/\n"
            "  src/engine/  [task_801_sample_feature.md] ...... PENDING\n"
            "  src/foo/     [task_803_foo.md] .................. PENDING  depends: 801\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = Path(tmpdir) / "MAP.md"
            map_path.write_text(map_content, encoding="utf-8")
            cfg = MapRewriteConfig(
                map_path=str(map_path),
                parent_id="task_801",
                subtask_ids=["task_801a", "task_801b", "task_801c"],
                last_subtask_id="task_801c",
                subtask_depends={"task_801a": [], "task_801b": ["task_801a"], "task_801c": ["task_801b"]},
            )
            new_content = rewrite_map_dependencies(cfg)
            self.assertIn("801c", new_content)
            self.assertNotIn("depends: 801\n", new_content)
            self.assertIn("task_801a_*.md", new_content)
            self.assertIn("task_801b_*.md", new_content)
            self.assertIn("task_801c_*.md", new_content)
            self.assertIn("depends: task_801a", new_content)
            self.assertIn("depends: task_801b", new_content)


class TestSingleStepPassthrough(unittest.TestCase):
    """Verify single-step task is not split."""

    def test_single_step_passthrough(self) -> None:
        single_step_content = _make_single_step_content()
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "task_802_single_step_task.md"
            task_path.write_text(single_step_content, encoding="utf-8")
            created = atomize_task(str(task_path))
            self.assertEqual(created, [])
            self.assertTrue(task_path.exists(), "Single-step task file must not be deleted")
            after = task_path.read_text(encoding="utf-8")
            self.assertEqual(after, single_step_content)


class TestMapRewriteLineFormatBasic(unittest.TestCase):
    """Verify MAP.md line formatting with prefix, padding, status, depends."""

    def test_extract_line_prefix(self) -> None:
        line = "  src/engine/  [task_801_model_registry.md] ...... PENDING"
        prefix = _extract_line_prefix(line)
        self.assertEqual(prefix, "  src/engine/  ")

    def test_build_active_task_line_with_depends(self) -> None:
        config = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="task_800",
        )
        line = _build_active_task_line(config)
        self.assertIn("[task_801a_*.md]", line)
        self.assertIn("PENDING", line)
        self.assertIn("depends: task_800", line)

    def test_build_active_task_line_no_depends(self) -> None:
        config = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="",
        )
        line = _build_active_task_line(config)
        self.assertIn("[task_801a_*.md]", line)
        self.assertIn("PENDING", line)
        self.assertNotIn("depends:", line)

    def test_subtask_line_has_prefix(self) -> None:
        config = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="",
        )
        line = _build_active_task_line(config)
        self.assertTrue(line.startswith("  src/engine/  "))

    def test_subtask_line_has_status(self) -> None:
        config = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="",
        )
        line = _build_active_task_line(config)
        self.assertIn("PENDING", line)

    def test_subtask_line_has_depends(self) -> None:
        config = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="task_800",
        )
        line = _build_active_task_line(config)
        self.assertIn("depends: task_800", line)


class TestMapRewriteFileDirectory(unittest.TestCase):
    """Verify File Directory section per sub-task in MAP.md."""

    def test_map_rewrite_with_file_directory(self) -> None:
        map_content = (
            "# MAP\n\n"
            "## Active Tasks\n\n"
            "Project/\n"
            "  src/engine/  [task_801_model_registry.md] ...... PENDING\n\n"
            "## File Directory\n\n"
            "### task_801 →\n"
            "Creates:\n"
            "  src/engine/model-registry.ts\n"
            "Modifies:\n"
            "  src/config.ts\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = Path(tmpdir) / "MAP.md"
            map_path.write_text(map_content, encoding="utf-8")
            parent_files = "Creates:\n  src/engine/model-registry.ts\nModifies:\n  src/config.ts"
            cfg = MapRewriteConfig(
                map_path=str(map_path),
                parent_id="task_801",
                subtask_ids=["task_801a", "task_801b"],
                last_subtask_id="task_801b",
                parent_files_section=parent_files,
                subtask_depends={"task_801a": [], "task_801b": ["task_801a"]},
            )
            new_content = rewrite_map_dependencies(cfg)
            self.assertIn("### task_801a →", new_content)
            self.assertIn("### task_801b →", new_content)
            self.assertNotIn("### task_801 →", new_content)


class TestMapRewriteLineFormatAdvanced(unittest.TestCase):
    """Verify per-sub-task MAP.md lines with correct depends."""

    def test_subtask_line_with_parent_depends(self) -> None:
        cfg = MapRewriteConfig(
            map_path="MAP.md",
            parent_id="task_801",
            subtask_ids=["task_801a", "task_801b"],
            last_subtask_id="task_801b",
            subtask_depends={"task_801a": ["task_800"], "task_801b": ["task_801a"]},
        )
        line_a = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801a_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="task_800",
        )
        built_a = _build_active_task_line(line_a)
        self.assertIn("task_801a_*.md", built_a)
        self.assertIn("depends: task_800", built_a)
        line_b = MapLineConfig(
            prefix="  src/engine/  ",
            task_filename="task_801b_*.md",
            padding_width=10,
            status="PENDING",
            depends_str="task_801a",
        )
        built_b = _build_active_task_line(line_b)
        self.assertIn("task_801b_*.md", built_b)
        self.assertIn("depends: task_801a", built_b)


class TestMapRewriteDirectoryPath(unittest.TestCase):
    """Verify File Directory extraction and per-subtask generation."""

    def test_extract_directory_from_header(self) -> None:
        parent_files = "### task_801 → src/engine/\nCreates:\n  model.ts"
        path = _extract_directory_from_parent_header(parent_files)
        self.assertEqual(path, "src/engine/")

    def test_build_file_directory_blocks(self) -> None:
        parent_files = "### task_801 → src/engine/\nCreates:\n  model.ts\nModifies:\n  config.ts"
        cfg = MapRewriteConfig(
            map_path="MAP.md",
            parent_id="task_801",
            subtask_ids=["task_801a", "task_801b"],
            last_subtask_id="task_801b",
            parent_files_section=parent_files,
        )
        blocks = _build_file_directory_block(cfg)
        self.assertIn("### task_801a → src/engine/", blocks)
        self.assertIn("### task_801b → src/engine/", blocks)
        self.assertIn("Creates:", blocks)


class TestRegexNegativeLookahead(unittest.TestCase):
    """Verify _map_replace_parent_entry does NOT match sub-task IDs."""

    def test_parent_pattern_skips_subtask_ids(self) -> None:
        """Pattern for task_801 must not match [task_801a_foo.md]."""
        map_content = (
            "  [task_801a_foo.md] .......... DONE\n"
            "  [task_801_bar.md] .......... PENDING\n"
        )
        cfg = MapRewriteConfig(
            map_path="MAP.md",
            parent_id="task_801",
            subtask_ids=["task_801x"],
            last_subtask_id="task_801x",
        )
        from scripts.atomize_task import _map_replace_parent_entry
        result = _map_replace_parent_entry(cfg, map_content)
        self.assertIn("task_801a_foo.md", result)
        self.assertNotIn("task_801_bar.md", result)


class TestAppendReviseEntryOrder(unittest.TestCase):
    """Verify REVISE entries append after existing entries, not before."""

    def test_new_entry_appends_after_existing(self) -> None:
        from scripts.orchestrate import _append_revise_entry
        content = (
            "## Registers\n"
            "REVISE round 1 (nonce 000000): first issue\n"
            "\n## Working Memory\n— empty —\n"
        )
        tmp = Path(tempfile.mktemp(suffix=".md"))
        tmp.write_text(content, encoding="utf-8")
        try:
            _append_revise_entry(str(tmp), "REVISE round 2 (nonce 000000): second issue")
            result = tmp.read_text(encoding="utf-8")
            first_pos = result.find("round 1")
            second_pos = result.find("round 2")
            self.assertGreater(second_pos, first_pos)
            self.assertIn("## Working Memory", result)
        finally:
            tmp.unlink(missing_ok=True)


class TestAtomizeRollback(unittest.TestCase):
    """Verify atomize_tasks rolls back on failure."""

    def test_rollback_removes_created_files(self) -> None:
        from scripts.atomize_task import AtomizeRequest, atomize_tasks
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            map_path = tmp / "MAP.md"
            map_content = "# MAP\n\n## Active Tasks\n\n  [task_901_good.md] ........ PENDING\n  [task_902_bad.md] ........ PENDING\n"
            map_path.write_text(map_content, encoding="utf-8")
            good_task = tmp / "task_901_good.md"
            good_task.write_text(
                "---\nid: task_901\nname: good\nstate: PENDING\nstep: 0 of 2\ndepends: []\n"
                "wave: 1\ndispatch: fsm-executor\ncheckpoint: aaa\ncreated: 2026-01-01\n---\n\n"
                "## Files\nCreates:\n  foo.py\n\n## Program\n1. First step\n2. Second step\n\n"
                "## Registers\n— empty —\n",
                encoding="utf-8",
            )
            bad_task = tmp / "task_902_bad.md"
            bad_task.write_text("not valid frontmatter", encoding="utf-8")
            request = AtomizeRequest(task_paths=[str(good_task), str(bad_task)], map_path=str(map_path))
            with self.assertRaises(ValueError):
                atomize_tasks(request)
            restored_map = map_path.read_text(encoding="utf-8")
            self.assertEqual(restored_map, map_content)
            subtask_files = list(tmp.glob("task_901a_*.md"))
            self.assertEqual(len(subtask_files), 0)


class TestMultiParentDepsRewrite(unittest.TestCase):
    """Verify atomize_tasks rewrites cross-parent depends to last-subtask IDs."""

    def test_later_parent_depends_updated_to_last_subtasks(self) -> None:
        from scripts.atomize_task import AtomizeRequest, atomize_tasks
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            map_path = tmp / "MAP.md"
            map_path.write_text(
                "# MAP\n\n## Active Tasks\n\n"
                "  [task_901_first.md] ........ PENDING\n"
                "  [task_902_second.md] ....... PENDING  depends: task_901\n",
                encoding="utf-8",
            )
            first = tmp / "task_901_first.md"
            first.write_text(
                "---\nid: task_901\nname: first\nstate: PENDING\nstep: 0 of 2\n"
                "depends: []\nwave: 1\ndispatch: fsm-executor\ncheckpoint: aaa\ncreated: 2026-01-01\n---\n\n"
                "## Files\nCreates:\n  a.py\n\n## Program\n1. First A\n2. First B\n",
                encoding="utf-8",
            )
            second = tmp / "task_902_second.md"
            second.write_text(
                "---\nid: task_902\nname: second\nstate: PENDING\nstep: 0 of 2\n"
                "depends: [task_901]\nwave: 2\ndispatch: fsm-integrator\ncheckpoint: bbb\ncreated: 2026-01-01\n---\n\n"
                "## Files\nModifies:\n  a.py\n\n## Program\n1. Second A\n2. Second B\n",
                encoding="utf-8",
            )
            request = AtomizeRequest(task_paths=[str(first), str(second)], map_path=str(map_path))
            atomize_tasks(request)
            subtask_902a = next(tmp.glob("task_902a_*.md"))
            content = subtask_902a.read_text(encoding="utf-8")
            self.assertIn("depends: [task_901b]", content)
            self.assertNotIn("depends: [task_901]", content)
            map_after = map_path.read_text(encoding="utf-8")
            self.assertIn("depends: task_901b", map_after)


if __name__ == "__main__":
    unittest.main()
