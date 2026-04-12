"""Tests for src/fsm_core/frontmatter.py — task file frontmatter parsing."""

import pytest

from src.fsm_core.frontmatter import TaskFrontmatter, parse_frontmatter


VALID_FRONTMATTER: str = """\
---
id: task_801
name: sample_feature
state: PENDING
step: 0 of 3
depends: [task_800]
wave: 2
dispatch: fsm-executor
checkpoint: abc123
created: 2026-01-01
---
"""

MINIMAL_FRONTMATTER: str = """\
---
id: task_001
name: minimal
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: 000000
created: 2026-01-01
---
"""

WITH_PARENT: str = """\
---
id: task_801a
name: sample_a
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: def456
created: 2026-01-01
parent: task_801
---
"""

WITH_USER_CONFIRM_TRUE: str = """\
---
id: task_802
name: confirm_true
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: ghi789
created: 2026-01-01
requires_user_confirmation: true
---
"""

WITH_USER_CONFIRM_FALSE: str = """\
---
id: task_803
name: confirm_false
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: jkl012
created: 2026-01-01
requires_user_confirmation: false
---
"""


class TestParseFrontmatter:
    def test_parses_all_required_fields(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert fm.id == "task_801"
        assert fm.name == "sample_feature"
        assert fm.state == "PENDING"
        assert fm.wave == 2
        assert fm.dispatch == "fsm-executor"
        assert fm.checkpoint == "abc123"

    def test_parses_depends_list(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert fm.depends == ["task_800"]

    def test_parses_empty_depends(self) -> None:
        fm = parse_frontmatter(MINIMAL_FRONTMATTER)
        assert fm.depends == []

    def test_parses_parent_field(self) -> None:
        fm = parse_frontmatter(WITH_PARENT)
        assert fm.parent == "task_801"

    def test_missing_parent_defaults_empty(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert fm.parent == ""

    def test_parses_requires_user_confirmation_true(self) -> None:
        fm = parse_frontmatter(WITH_USER_CONFIRM_TRUE)
        assert fm.requires_user_confirmation is True

    def test_parses_requires_user_confirmation_false(self) -> None:
        fm = parse_frontmatter(WITH_USER_CONFIRM_FALSE)
        assert fm.requires_user_confirmation is False

    def test_missing_requires_user_confirmation_defaults_false(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert fm.requires_user_confirmation is False

    def test_missing_delimiters_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed frontmatter"):
            parse_frontmatter("no delimiters here")

    def test_missing_required_field_raises(self) -> None:
        broken = """\
---
id: task_001
name: broken
---
"""
        with pytest.raises(ValueError, match="Missing frontmatter fields"):
            parse_frontmatter(broken)

    def test_multi_depends(self) -> None:
        content = VALID_FRONTMATTER.replace("depends: [task_800]", "depends: [task_800, task_799]")
        fm = parse_frontmatter(content)
        assert fm.depends == ["task_800", "task_799"]

    def test_returns_task_frontmatter_type(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert isinstance(fm, TaskFrontmatter)

    def test_atomize_defaults_to_optional(self) -> None:
        fm = parse_frontmatter(VALID_FRONTMATTER)
        assert fm.atomize == "optional"

    def test_parses_atomize_required(self) -> None:
        content = VALID_FRONTMATTER.replace("checkpoint: abc123", "checkpoint: abc123\natomize: required")
        fm = parse_frontmatter(content)
        assert fm.atomize == "required"

    def test_parses_atomize_skip(self) -> None:
        content = VALID_FRONTMATTER.replace("checkpoint: abc123", "checkpoint: abc123\natomize: skip")
        fm = parse_frontmatter(content)
        assert fm.atomize == "skip"
