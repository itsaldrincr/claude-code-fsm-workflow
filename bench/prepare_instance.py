"""Prepare isolated SWE-bench instances for evaluation.

Creates isolated temp workspaces, initializes git baseline,
and renders instance spec files from templates.
Stdlib only.
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from bench.config import BENCH_DEFAULT_WORKSPACE_ROOT

logger = logging.getLogger(__name__)


@dataclass
class PrepareInstanceRequest:
    """Request to prepare an instance."""
    instance_id: str
    source_dir: Path | str
    workspace_root: Path | str | None
    problem_statement: str
    hints: str
    target_files: str
    acceptance_criteria: str


@dataclass
class PrepareResult:
    """Result of instance preparation."""
    workspace_path: Path
    baseline_commit_sha: str
    spec_file_path: Path


def prepare_instance(request: PrepareInstanceRequest) -> PrepareResult:
    """Prepare an isolated instance workspace."""
    workspace_root = Path(request.workspace_root or BENCH_DEFAULT_WORKSPACE_ROOT)
    workspace_path = _create_workspace(workspace_root, request.instance_id)
    _copy_sources(Path(request.source_dir), workspace_path)
    baseline_sha = _init_git_baseline(workspace_path)
    spec_path = _write_spec_file(workspace_path, request)
    logger.info("Prepared %s at %s (baseline: %s)", request.instance_id, workspace_path, baseline_sha)
    return PrepareResult(workspace_path=workspace_path, baseline_commit_sha=baseline_sha, spec_file_path=spec_path)


def _create_workspace(workspace_root: Path, instance_id: str) -> Path:
    """Create isolated temp workspace under root/instance_id."""
    workspace_root.mkdir(parents=True, exist_ok=True)
    instance_dir = workspace_root / instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Created workspace at %s", instance_dir)
    return instance_dir


def _copy_sources(source_dir: Path, workspace_path: Path) -> None:
    """Copy all sources from source_dir to workspace, excluding .git."""
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    for item in source_dir.iterdir():
        if item.name == ".git":
            continue
        dest = workspace_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    logger.debug("Copied sources from %s to %s", source_dir, workspace_path)


def _init_git_baseline(workspace_path: Path) -> str:
    """Initialize git repo, add all files, commit as baseline.

    Returns baseline commit SHA.
    """
    subprocess.run(["git", "init"], cwd=workspace_path, check=True)
    subprocess.run(["git", "config", "user.email", "swe-bench@local"], cwd=workspace_path, check=True)
    subprocess.run(["git", "config", "user.name", "SWE-Bench"], cwd=workspace_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "swe-bench baseline"],
        cwd=workspace_path, check=True
    )

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace_path, capture_output=True, text=True, check=True
    )
    commit_sha = result.stdout.strip()
    logger.debug("Git baseline commit: %s", commit_sha)
    return commit_sha


def _write_spec_file(workspace_path: Path, request: PrepareInstanceRequest) -> Path:
    """Render spec template and write to workspace."""
    template_path = Path(__file__).parent / "templates" / "spec_template.md"
    template = template_path.read_text()

    spec_content = template.format(
        instance_id=request.instance_id,
        problem_statement=request.problem_statement,
        hints=request.hints,
        target_files=request.target_files,
        acceptance_criteria=request.acceptance_criteria
    )

    spec_file_path = workspace_path / "SPEC.md"
    spec_file_path.write_text(spec_content)
    logger.debug("Wrote spec file to %s", spec_file_path)
    return spec_file_path
