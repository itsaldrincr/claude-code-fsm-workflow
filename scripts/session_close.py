"""Session cleanup: reset MAP.md, delete task files, delete audit sentinel."""

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON_EXECUTABLE: str = sys.executable
TEST_DIR: str = "tests/"
SUBPROCESS_TIMEOUT_SECONDS: int = 600

logger = logging.getLogger(__name__)

CLEAN_MAP_TEMPLATE: str = """# MAP

## Active Tasks

— none —

## Completed (awaiting audit)

— none —

## File Directory

— none —
"""

AUDIT_SENTINEL: str = ".audit_clean"
EXIT_CLEAN: int = 0
EXIT_FAILED: int = 1
EXIT_ERROR: int = 2


@dataclass(frozen=True)
class CloseConfig:
    """Configuration for session cleanup."""

    workspace: Path
    is_dry_run: bool = False


@dataclass(frozen=True)
class CloseResult:
    """Result of session cleanup."""

    exit_code: int
    detail: str


def _parse_args() -> CloseConfig:
    """Parse command-line arguments and return CloseConfig."""
    parser = argparse.ArgumentParser(description="Reset session state: MAP.md, task files, sentinel.")
    parser.add_argument("--workspace", default=".", type=Path, help="Workspace root (default: current dir)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    args = parser.parse_args()
    return CloseConfig(workspace=args.workspace, is_dry_run=args.dry_run)


def _run_tests(workspace: Path) -> subprocess.CompletedProcess:
    """Run pytest suite and return CompletedProcess."""
    try:
        return subprocess.run(
            [PYTHON_EXECUTABLE, "-m", "pytest", TEST_DIR, "-v"],
            cwd=workspace,
            capture_output=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.error("Test run timed out after %d seconds", SUBPROCESS_TIMEOUT_SECONDS)
        raise


def _delete_task_files(workspace: Path) -> None:
    """Delete all task_*.md files in workspace root."""
    for task_file in workspace.glob("task_*.md"):
        if not task_file.is_file():
            continue
        logger.info("Deleting task file: %s", task_file.name)
        task_file.unlink()


def _reset_map(workspace: Path) -> None:
    """Overwrite MAP.md with clean template."""
    map_path = workspace / "MAP.md"
    logger.info("Resetting MAP.md")
    map_path.write_text(CLEAN_MAP_TEMPLATE)


def _delete_sentinel(workspace: Path) -> None:
    """Delete .audit_clean sentinel if present."""
    sentinel_path = workspace / AUDIT_SENTINEL
    if sentinel_path.exists():
        logger.info("Deleting audit sentinel: %s", AUDIT_SENTINEL)
        sentinel_path.unlink()


def _run_close(config: CloseConfig) -> CloseResult:
    """Orchestrate session close: run tests, cleanup files, reset state."""
    test_result = _run_tests(config.workspace)
    if test_result.returncode != 0:
        return CloseResult(exit_code=EXIT_FAILED, detail="Tests failed; cleanup aborted")

    if config.is_dry_run:
        logger.info("Dry-run: would delete task files, reset MAP, delete sentinel")
        return CloseResult(exit_code=EXIT_CLEAN, detail="Dry-run complete")

    _delete_task_files(config.workspace)
    _reset_map(config.workspace)
    _delete_sentinel(config.workspace)
    return CloseResult(exit_code=EXIT_CLEAN, detail="Session cleanup complete")


def main() -> None:
    """Parse args, run close, log result, exit with result code."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = _parse_args()
    result = _run_close(config)
    logger.info(result.detail)
    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
