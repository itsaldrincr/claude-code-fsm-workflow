"""Integration tests for prepare_instance."""

import json
import subprocess
from pathlib import Path

import pytest

from bench.prepare_instance import PrepareInstanceRequest, prepare_instance


@pytest.fixture
def tiny_instance_source(tmp_path: Path) -> Path:
    """Create a temporary instance source directory for testing."""
    source = tmp_path / "tiny_source"
    source.mkdir()

    src_dir = source / "src"
    src_dir.mkdir()
    (src_dir / "hello.py").write_text("def hello():\n    return 'Hello, World!'\n")

    metadata = {
        "instance_id": "test-001",
        "problem_statement": "Test problem",
        "hints": "Test hints",
        "target_files": "src/hello.py",
        "acceptance_criteria": "Test passes"
    }
    (source / "metadata.json").write_text(json.dumps(metadata))

    return source


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    """Create a temporary workspace root for testing."""
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


def test_prepare_instance_creates_workspace(tiny_instance_source: Path, workspace_root: Path) -> None:
    """Test that prepare_instance creates an isolated workspace."""
    request = PrepareInstanceRequest(
        instance_id="test-001",
        source_dir=tiny_instance_source,
        workspace_root=workspace_root,
        problem_statement="Test problem",
        hints="Test hints",
        target_files="src/hello.py",
        acceptance_criteria="Test passes"
    )

    result = prepare_instance(request)

    assert result.workspace_path.exists()
    assert result.workspace_path.name == "test-001"
    assert result.workspace_path.parent == workspace_root


def test_prepare_instance_git_baseline_exists(tiny_instance_source: Path, workspace_root: Path) -> None:
    """Test that prepare_instance creates git baseline commit."""
    request = PrepareInstanceRequest(
        instance_id="test-002",
        source_dir=tiny_instance_source,
        workspace_root=workspace_root,
        problem_statement="Test problem",
        hints="Test hints",
        target_files="src/hello.py",
        acceptance_criteria="Test passes"
    )

    result = prepare_instance(request)

    git_dir = result.workspace_path / ".git"
    assert git_dir.exists()

    log_result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=result.workspace_path,
        capture_output=True,
        text=True,
        check=True
    )
    assert "swe-bench baseline" in log_result.stdout

    assert len(result.baseline_commit_sha) == 40
    assert result.baseline_commit_sha.isalnum()


def test_prepare_instance_spec_file_populated(tiny_instance_source: Path, workspace_root: Path) -> None:
    """Test that spec file is rendered with populated placeholders."""
    request = PrepareInstanceRequest(
        instance_id="test-003",
        source_dir=tiny_instance_source,
        workspace_root=workspace_root,
        problem_statement="Fix the broken logic",
        hints="Check the return value",
        target_files="src/main.py, src/util.py",
        acceptance_criteria="All tests pass"
    )

    result = prepare_instance(request)

    assert result.spec_file_path.exists()
    spec_content = result.spec_file_path.read_text()

    assert "Fix the broken logic" in spec_content
    assert "Check the return value" in spec_content
    assert "src/main.py, src/util.py" in spec_content
    assert "All tests pass" in spec_content
    assert "test-003" in spec_content
