"""Deterministic wave gate: derives touched files, runs audits, returns APPROVE or UNDETERMINED."""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]

logger = logging.getLogger(__name__)

GATE_APPROVE = "APPROVE"
GATE_UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class GateResult:
    """Result of a deterministic wave evaluation.

    Attributes:
        verdict: str, either GATE_APPROVE or GATE_UNDETERMINED.
        detail: str, human-readable summary of the gate decision.
        touched_files: tuple[str, ...], sorted and deduped paths created/modified by the wave.
    """

    verdict: str
    detail: str
    touched_files: tuple[str, ...]


def _extract_file_path(line: str) -> str:
    """Extract file path from a line like 'path/file.ts  # comment'."""
    return line.split("#")[0].strip()


def _collect_files_from_section(section: str) -> tuple[list[str], list[str]]:
    """Collect Creates and Modifies paths from ## Files section."""
    creates, modifies, current = [], [], None
    for line in section.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("creates:"):
            current = "creates"
        elif s.lower().startswith("modifies:"):
            current = "modifies"
        elif s.lower().startswith("reads:"):
            current = None
        elif current:
            path = _extract_file_path(s)
            if path:
                (creates if current == "creates" else modifies).append(path)
    return creates, modifies


def _read_files_section(content: str) -> str:
    """Extract ## Files section from task content."""
    lines = content.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## Files")), -1)
    if start < 0:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("##")), len(lines))
    return "\n".join(lines[start + 1:end])


def _gather_task_files(task_path: str) -> tuple[list[str], list[str]]:
    """Load task file and extract Creates/Modifies paths."""
    try:
        with open(task_path, encoding="utf-8") as f:
            content = f.read()
    except (FileNotFoundError, OSError) as exc:
        logger.warning("Could not read task file %s: %s", task_path, exc)
        return [], []
    section = _read_files_section(content)
    return _collect_files_from_section(section) if section else ([], [])


def _derive_touched_files(task_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Derive touched files from task frontmatter and Files sections.

    Reads each task file, parses frontmatter and ## Files section,
    collects all Creates and Modifies paths, sorts and dedupes.

    Args:
        task_paths: tuple of absolute task file paths.

    Returns:
        sorted, deduped tuple of all touched file paths.
    """
    touched: set[str] = set()
    for task_path in task_paths:
        creates, modifies = _gather_task_files(task_path)
        touched.update(creates)
        touched.update(modifies)
    return tuple(sorted(touched))


def _run_audit_discipline(files: tuple[str, ...]) -> tuple[int, str]:
    """Run audit_discipline on files. Returns (exit_code, error_message)."""
    try:
        result = subprocess.run(
            ["python", str(_REPO_ROOT / "scripts" / "audit_discipline.py")] + list(files),
            capture_output=True,
            text=True,
        )
        return result.returncode, ""
    except Exception as exc:
        return -1, f"subprocess error in audit_discipline: {exc}"


def _run_check_deps(files: tuple[str, ...]) -> tuple[int, str]:
    """Run check_deps on files. Returns (exit_code, error_message)."""
    try:
        result = subprocess.run(
            ["python", str(_REPO_ROOT / "scripts" / "check_deps.py")] + list(files),
            capture_output=True,
            text=True,
        )
        return result.returncode, ""
    except Exception as exc:
        return -1, f"subprocess error in check_deps: {exc}"


def _run_pytest_wave(task_paths: tuple[str, ...], touched_files: tuple[str, ...]) -> tuple[int, str]:
    """Run pytest on touched test files. Returns (exit_code, error_message)."""
    if not touched_files:
        return 0, ""
    test_files = [
        str(_REPO_ROOT / f)
        for f in touched_files
        if f.startswith("tests/") and f.endswith(".py")
    ]
    if not test_files:
        return 0, ""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest"] + test_files + ["-v"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        return result.returncode, ""
    except Exception as exc:
        return -1, f"subprocess error in pytest: {exc}"


def _run_gate_pipeline(touched_files: tuple[str, ...], task_paths: tuple[str, ...]) -> GateResult:
    """Run the three subprocess audits in sequence. Return result of first failure or APPROVE."""
    discipline_rc, discipline_err = _run_audit_discipline(touched_files)
    if discipline_rc != 0:
        detail = discipline_err if discipline_err else "discipline audit failed"
        return GateResult(GATE_UNDETERMINED, detail, touched_files)
    deps_rc, deps_err = _run_check_deps(touched_files)
    if deps_rc != 0:
        detail = deps_err if deps_err else "dependency check failed"
        return GateResult(GATE_UNDETERMINED, detail, touched_files)
    pytest_rc, pytest_err = _run_pytest_wave(task_paths, touched_files)
    if pytest_rc != 0:
        detail = pytest_err if pytest_err else "pytest failed"
        return GateResult(GATE_UNDETERMINED, detail, touched_files)
    return GateResult(GATE_APPROVE, "all deterministic checks passed", touched_files)


def evaluate_wave(task_paths: tuple[str, ...]) -> GateResult:
    """Evaluate a wave via deterministic audits (discipline, deps, tests).

    Derives touched files from task_paths, runs audit_discipline, check_deps,
    and targeted pytest. Returns APPROVE if all three exit 0, else UNDETERMINED.
    Never returns REVISE.

    Args:
        task_paths: tuple of absolute task file paths.

    Returns:
        GateResult with verdict GATE_APPROVE or GATE_UNDETERMINED.
    """
    touched_files = _derive_touched_files(task_paths)
    if not touched_files:
        return GateResult(GATE_APPROVE, "no touched files", ())
    return _run_gate_pipeline(touched_files, task_paths)
