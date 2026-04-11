"""Unit tests for run_one module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from bench.run_one import RunOneRequest, RunOneResult, run_one


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Create a minimal git workspace with a committed baseline."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=workspace, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=workspace, check=True, capture_output=True,
    )
    (workspace / "dummy.py").write_text("# initial\n")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=workspace, check=True, capture_output=True,
    )
    return workspace


@pytest.fixture
def pass_request(git_workspace: Path) -> RunOneRequest:
    """RunOneRequest targeting a git workspace, exit-0 scenario."""
    return RunOneRequest(
        workspace_path=git_workspace,
        instance_id="test-pass-001",
        expected_patch="",
        orchestrate_script=Path("scripts/orchestrate.py"),
    )


def test_run_one_pass_returns_run_one_result(pass_request: RunOneRequest) -> None:
    """run_one against mocked exit-0 subprocess returns a RunOneResult."""
    with patch("bench.run_one._run_orchestrate_once", return_value=0):
        result = run_one(pass_request)

    assert isinstance(result, RunOneResult)
    assert result.instance_id == "test-pass-001"
    assert result.status == "pass"
    assert result.exit_code == 0
    assert isinstance(result.eval_score, float)
    assert result.eval_score >= 0.0


def test_run_one_pass_writes_valid_bench_result_json(pass_request: RunOneRequest) -> None:
    """run_one on exit 0 writes bench_result.json with required keys."""
    with patch("bench.run_one._run_orchestrate_once", return_value=0):
        result = run_one(pass_request)

    assert result.bench_result_path.exists()
    data = json.loads(result.bench_result_path.read_text())
    assert data["instance_id"] == "test-pass-001"
    assert data["status"] == "pass"
    assert data["exit_code"] == 0
    assert "eval_score" in data
    assert "captured_patch" in data


def test_run_one_fail_on_exit_blocked(git_workspace: Path) -> None:
    """Exit code 3 (BLOCKED) produces status=fail and empty captured_patch."""
    request = RunOneRequest(
        workspace_path=git_workspace,
        instance_id="test-fail-002",
        expected_patch="",
        orchestrate_script=Path("scripts/orchestrate.py"),
    )
    with patch("bench.run_one._run_orchestrate_once", return_value=3):
        result = run_one(request)

    assert result.status == "fail"
    assert result.exit_code == 3
    assert result.captured_patch == ""
    assert result.eval_score == -1.0
    assert result.bench_result_path.exists()


def test_run_one_retry_once_calls_orchestrate_twice(git_workspace: Path) -> None:
    """Exit code 4 triggers retry_once; a second exit 4 exhausts retry and fails."""
    request = RunOneRequest(
        workspace_path=git_workspace,
        instance_id="test-retry-003",
        expected_patch="",
        orchestrate_script=Path("scripts/orchestrate.py"),
    )
    with patch("bench.run_one._run_orchestrate_once", return_value=4) as mock_run:
        result = run_one(request)

    assert mock_run.call_count == 2
    assert result.status == "fail"
    assert result.exit_code == 4
