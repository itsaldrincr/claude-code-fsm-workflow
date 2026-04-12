"""Tests for split_claude_md helper."""

import tempfile
from pathlib import Path

import pytest

from scripts.split_claude_md import split, SplitRequest

REPO_ROOT = Path(__file__).resolve().parent.parent
FULL_CLAUDE_MD = REPO_ROOT / 'CLAUDE.md'
COMMITTED_DIR = REPO_ROOT / 'plugins' / 'fsm-workflow'


@pytest.mark.skipif(not FULL_CLAUDE_MD.exists(), reason="Full CLAUDE.md not present (only available in harness repo)")
def test_split_matches_committed_artifacts():
    """Invoke split in tempdir and diff output against committed artifacts."""
    local_claude = FULL_CLAUDE_MD
    committed_dir = COMMITTED_DIR

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        request = SplitRequest(source=local_claude, output_dir=output_dir)
        result = split(request)

        assert result.slim_template.exists()
        assert len(result.skills) == 6

        for skill_path in result.skills:
            assert skill_path.exists()

        slim_template_path = committed_dir / 'templates' / 'CLAUDE.md'
        actual_slim = result.slim_template.read_text()
        expected_slim = slim_template_path.read_text()
        assert actual_slim == expected_slim, "slim template does not match committed"

        committed_skills_dir = committed_dir / 'skills'
        for skill_path in result.skills:
            committed_path = committed_skills_dir / skill_path.name
            actual_content = skill_path.read_text()
            expected_content = committed_path.read_text()
            assert actual_content == expected_content, f"{skill_path.name} does not match committed"
