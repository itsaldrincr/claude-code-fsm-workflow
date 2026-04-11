"""Run a single SWE-bench instance through the FSM orchestrator loop."""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from bench.config import BENCH_EVAL_BACKEND, BENCH_INSTANCE_TIMEOUT_SECONDS, BENCH_RETRY_POLICY
from bench.evaluate import EvaluationRequest, evaluate
from scripts.orchestrate import (
    EXIT_ACTION_TAKEN,
    EXIT_ALL_DONE,
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_WAITING,
    SUBPROCESS_TIMEOUT_SECONDS,
)
from src.fsm_core.map_reader import ReadTasksRequest, TaskInfo, read_task_dispatch_info

logger = logging.getLogger(__name__)

_LOOP_CONTINUE_CODES: frozenset[int] = frozenset({EXIT_ACTION_TAKEN, EXIT_WAITING})

PolicyAction = Literal["continue", "pass", "fail"]


@dataclass
class RunOneRequest:
    """Request parameters for a single benchmark instance run."""

    workspace_path: Path
    instance_id: str
    expected_patch: str
    orchestrate_script: Path
    timeout_seconds: int = BENCH_INSTANCE_TIMEOUT_SECONDS
    result_dir: Path | None = None


@dataclass
class RunOneResult:
    """Result of a single benchmark instance run."""

    instance_id: str
    status: str
    exit_code: int
    captured_patch: str
    eval_score: float
    task_states: list[TaskInfo]
    bench_result_path: Path


def run_one(request: RunOneRequest) -> RunOneResult:
    """Run orchestrator loop against a prepared workspace and return result."""
    final_exit_code = _drive_orchestrate_loop(request)
    patch = _capture_patch(request.workspace_path) if final_exit_code == EXIT_ALL_DONE else ""
    task_states = _query_final_states(request.workspace_path)
    policy = BENCH_RETRY_POLICY.get(final_exit_code, "fail")
    status = "pass" if policy == "pass" else "fail"
    eval_score = _evaluate_patch(request.expected_patch, patch) if status == "pass" else -1.0
    result_dir = request.result_dir if request.result_dir is not None else request.workspace_path
    result_path = result_dir / "bench_result.json"
    result = RunOneResult(
        instance_id=request.instance_id,
        status=status,
        exit_code=final_exit_code,
        captured_patch=patch,
        eval_score=eval_score,
        task_states=task_states,
        bench_result_path=result_path,
    )
    _emit_result_json(result, result_path)
    return result


def _drive_orchestrate_loop(request: RunOneRequest) -> int:
    """Run orchestrate.py in a loop until a terminal exit code is returned."""
    deadline = time.monotonic() + request.timeout_seconds
    has_retried = False
    while time.monotonic() < deadline:
        exit_code = _run_orchestrate_once(request.workspace_path, request.orchestrate_script)
        action, has_retried = _dispatch_exit_policy(exit_code, has_retried)
        if action != "continue":
            logger.info(
                "Instance %s loop terminal: exit=%d action=%s",
                request.instance_id, exit_code, action,
            )
            return exit_code
    logger.warning("Instance %s timed out after %ds", request.instance_id, request.timeout_seconds)
    return EXIT_BLOCKED


def _dispatch_exit_policy(exit_code: int, has_retried: bool) -> tuple[PolicyAction, bool]:
    """Return (action, updated_has_retried) for the given exit code and retry state."""
    if exit_code in _LOOP_CONTINUE_CODES:
        return "continue", has_retried
    policy = BENCH_RETRY_POLICY.get(exit_code, "fail")
    if policy == "retry_once" and not has_retried:
        return "continue", True
    if policy == "pass":
        return "pass", has_retried
    return "fail", has_retried


def _capture_patch(workspace_path: Path) -> str:
    """Capture binary git diff against HEAD baseline."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--binary"],
            cwd=workspace_path,
            capture_output=True,
            check=True,
        )
        return result.stdout.decode(errors="replace")
    except subprocess.CalledProcessError as exc:
        logger.warning("git diff failed in %s: %s", workspace_path, exc)
        return ""


def _evaluate_patch(expected_patch: str, captured_patch: str) -> float:
    """Evaluate captured patch against expected and return similarity score."""
    req = EvaluationRequest(
        expected_patch=expected_patch,
        captured_patch=captured_patch,
        backend=BENCH_EVAL_BACKEND,
    )
    return evaluate(req).score


def _emit_result_json(result: RunOneResult, output_path: Path) -> None:
    """Write bench_result.json for the completed instance run."""
    data: dict[str, object] = {
        "instance_id": result.instance_id,
        "status": result.status,
        "exit_code": result.exit_code,
        "captured_patch": result.captured_patch,
        "eval_score": result.eval_score,
        "task_count": len(result.task_states),
        "task_states": [f"{t.task_id}:{t.status}" for t in result.task_states],
    }
    output_path.write_text(json.dumps(data, indent=2))
    logger.info("Wrote bench result to %s", output_path)


def _run_orchestrate_once(workspace_path: Path, script_path: Path) -> int:
    """Run orchestrate.py once and return its exit code."""
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), "--workspace", str(workspace_path)],
            capture_output=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.error("orchestrate.py subprocess timed out in %s", workspace_path)
        return EXIT_BLOCKED
    except Exception as exc:
        logger.error("orchestrate.py subprocess error: %s", exc)
        return EXIT_ERROR


def _query_final_states(workspace_path: Path) -> list[TaskInfo]:
    """Query final task states from MAP.md after orchestration completes."""
    map_path = workspace_path / "MAP.md"
    if not map_path.exists():
        logger.warning("MAP.md not found at %s", map_path)
        return []
    req = ReadTasksRequest(workspace=workspace_path, map_path=map_path)
    return read_task_dispatch_info(req)
