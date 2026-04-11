"""CLI entry point that wires all fsm_core modules into a single dispatch cycle."""

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.fsm_core.action_decider import (
    ALL_DONE,
    DISPATCH_ADVISOR,
    DISPATCH_WAVE,
    ESCALATE_BLOCKED,
    WAITING,
    Action,
    PipelineState,
    TaskStatus,
    decide_action,
)
from src.fsm_core.advisor_parser import (
    MAX_REVISE_ROUNDS,
    ReviseEntryConfig,
    build_revise_register_entry,
    count_revise_rounds,
    parse_advisor_output,
)
from src.fsm_core.map_io import StatusUpdateRequest, update_map_status
from src.fsm_core.map_lock import LockTimeoutError, map_lock
from src.fsm_core.map_reader import ReadTasksRequest, TaskInfo, read_task_dispatch_info
from src.fsm_core.subprocess_dispatch import (
    AdvisorDispatchRequest,
    ReviseDispatchRequest,
    WorkerDispatchRequest,
    dispatch_advisor,
    dispatch_revise,
    dispatch_worker,
)

logger = logging.getLogger(__name__)

EXIT_ALL_DONE: int = 0
EXIT_ACTION_TAKEN: int = 1
EXIT_WAITING: int = 2
EXIT_BLOCKED: int = 3
EXIT_ERROR: int = 4
EXIT_AUDIT_FAILED: int = 5

AUDIT_SENTINEL: str = ".audit_clean"
REGISTERS_SECTION: str = "## Registers"
NONCE_PLACEHOLDER: str = "000000"
GUIDANCE_SUMMARY_LIMIT: int = 100
AUDIT_DISCIPLINE_SCRIPT: str = "scripts/audit_discipline.py"
CHECK_DEPS_SCRIPT: str = "scripts/check_deps.py"
SESSION_CLOSE_SCRIPT: str = "scripts/session_close.py"
AUDIT_SRC_DIR: str = "src"
AUDIT_SCRIPTS_DIR: str = "scripts"
PYTHON_EXECUTABLE: str = sys.executable
SUBPROCESS_TIMEOUT_SECONDS: int = 600


@dataclass
class OrchestrateConfig:
    """Configuration for a single orchestration cycle."""

    workspace: Path
    is_dry_run: bool


@dataclass
class ActionResult:
    """Result of a single orchestration cycle."""

    exit_code: int
    output: dict[str, str]


@dataclass
class CycleContext:
    """Shared context threaded through all cycle handlers."""

    config: OrchestrateConfig
    map_path: Path
    task_lookup: dict[str, TaskInfo]


@dataclass
class ReviseContext:
    """Context for handling an advisor REVISE verdict."""

    task_id: str
    info: TaskInfo
    guidance: str


@dataclass(frozen=True)
class AuditGateResult:
    """Result of running audit scripts as a gate."""

    is_clean: bool
    detail: str


@dataclass(frozen=True)
class AuditScriptRequest:
    """Parameters for running a single audit script subprocess."""

    cmd: list[str]
    env: dict[str, str]


def main() -> int:
    """Parse args, run one orchestration cycle, print JSON, return exit code."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    config = OrchestrateConfig(workspace=Path(args.workspace), is_dry_run=args.dry_run)
    try:
        result = _run_cycle(config)
    except Exception as exc:
        logger.error("Unhandled error in orchestration cycle: %s", exc)
        result = ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": str(exc)})
    if result.output:
        sys.stdout.write(json.dumps(result.output) + "\n")
    return result.exit_code


def _parse_args() -> argparse.Namespace:
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(description="FSM orchestrator dispatch loop")
    parser.add_argument("--workspace", default=".", help="Workspace root containing MAP.md")
    parser.add_argument("--dry-run", action="store_true", help="Print planned action without executing")
    return parser.parse_args()


def _build_pipeline_state(tasks: list[TaskInfo]) -> PipelineState:
    """Convert TaskInfo list to PipelineState."""
    statuses = [
        TaskStatus(
            task_id=t.task_id,
            status=t.status,
            dispatch_role=t.dispatch_role,
            depends=t.depends,
        )
        for t in tasks
    ]
    return PipelineState(tasks=statuses)


def _run_cycle(config: OrchestrateConfig) -> ActionResult:
    """Read pipeline state, decide action, execute it, return result."""
    map_path = config.workspace / "MAP.md"
    if not map_path.exists():
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": "MAP.md not found"})
    try:
        request = ReadTasksRequest(workspace=config.workspace, map_path=map_path)
        tasks = read_task_dispatch_info(request)
    except (FileNotFoundError, LockTimeoutError) as exc:
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": str(exc)})

    state = _build_pipeline_state(tasks)
    action = decide_action(state)
    ctx = CycleContext(config=config, map_path=map_path, task_lookup={t.task_id: t for t in tasks})
    return _dispatch_action(action, ctx)


def _dispatch_action(action: Action, ctx: CycleContext) -> ActionResult:
    """Route action to the appropriate handler."""
    if action.kind == ESCALATE_BLOCKED:
        return _handle_escalate(action)
    if action.kind == DISPATCH_ADVISOR:
        return _handle_dispatch_advisor(action, ctx)
    if action.kind == DISPATCH_WAVE:
        return _handle_dispatch_wave(action, ctx)
    if action.kind == ALL_DONE:
        return _handle_all_done(ctx)
    if action.kind == WAITING:
        return _handle_waiting()
    return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": f"Unknown action: {action.kind}"})


def _handle_escalate(action: Action) -> ActionResult:
    """Return BLOCKED exit with escalation detail."""
    detail = f"{', '.join(action.tasks)} BLOCKED after {MAX_REVISE_ROUNDS} advisor REVISE rounds"
    output = {"action": "escalate", "tasks": action.tasks, "detail": detail}
    return ActionResult(EXIT_BLOCKED, output)


def _has_audit_sentinel(workspace: Path) -> bool:
    """Return True if the audit sentinel file exists in workspace."""
    return (workspace / AUDIT_SENTINEL).exists()


def _decode_result_output(result: subprocess.CompletedProcess) -> str:
    """Return non-empty stdout or stderr from a completed subprocess."""
    stdout = result.stdout.decode(errors="replace").strip()
    stderr = result.stderr.decode(errors="replace").strip()
    return stdout or stderr or "(no output)"


def _run_one_audit_script(request: AuditScriptRequest, workspace: Path) -> AuditGateResult | None:
    """Run a single audit script; return AuditGateResult on failure, None on success."""
    script_name = request.cmd[1] if len(request.cmd) > 1 else "audit script"
    try:
        result = subprocess.run(
            request.cmd, cwd=workspace, capture_output=True,
            env=request.env, timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return AuditGateResult(is_clean=False, detail=f"{script_name} timed out")
    if result.returncode != 0:
        detail_text = _decode_result_output(result)
        return AuditGateResult(is_clean=False, detail=f"{script_name} failed: {detail_text}")
    return None


def _run_audit_scripts(workspace: Path) -> AuditGateResult:
    """Run audit_discipline.py and check_deps.py; return AuditGateResult."""
    env = {**os.environ, "PYTHONPATH": str(workspace)}
    discipline_req = AuditScriptRequest(
        cmd=[PYTHON_EXECUTABLE, AUDIT_DISCIPLINE_SCRIPT, AUDIT_SRC_DIR, AUDIT_SCRIPTS_DIR],
        env=env,
    )
    failure = _run_one_audit_script(discipline_req, workspace)
    if failure is not None:
        return failure
    deps_req = AuditScriptRequest(
        cmd=[PYTHON_EXECUTABLE, CHECK_DEPS_SCRIPT, AUDIT_SRC_DIR, AUDIT_SCRIPTS_DIR],
        env=env,
    )
    failure = _run_one_audit_script(deps_req, workspace)
    if failure is not None:
        return failure
    return AuditGateResult(is_clean=True, detail="audit clean")


def _write_audit_sentinel(workspace: Path) -> None:
    """Create the .audit_clean sentinel file in workspace."""
    (workspace / AUDIT_SENTINEL).touch()


def _run_session_close(workspace: Path) -> bool:
    """Run session_close.py via subprocess. Returns True on success."""
    try:
        result = subprocess.run(
            [PYTHON_EXECUTABLE, SESSION_CLOSE_SCRIPT, "--workspace", str(workspace)],
            cwd=workspace,
            capture_output=False,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.error("session_close.py timed out")
        return False
    if result.returncode != 0:
        logger.error("session_close.py exited %d", result.returncode)
        return False
    return True


def _run_audit_if_needed(workspace: Path) -> AuditGateResult | None:
    """Check sentinel under lock; run audit and write sentinel if absent. Returns None if already clean."""
    with map_lock(workspace / "MAP.md"):
        if _has_audit_sentinel(workspace):
            return None
        audit_result = _run_audit_scripts(workspace)
        if audit_result.is_clean:
            _write_audit_sentinel(workspace)
        return audit_result


def _handle_all_done(ctx: CycleContext) -> ActionResult:
    """Run audit gate then session close when all tasks are DONE."""
    if ctx.config.is_dry_run:
        logger.info("DRY-RUN: would run audit gate and session_close")
        return ActionResult(EXIT_ALL_DONE, {})
    workspace = ctx.config.workspace
    audit_result = _run_audit_if_needed(workspace)
    if audit_result is not None and not audit_result.is_clean:
        logger.error("Audit gate failed: %s", audit_result.detail)
        return ActionResult(EXIT_AUDIT_FAILED, {"action": "audit_failed", "tasks": [], "detail": audit_result.detail})
    if not _run_session_close(workspace):
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": "session_close failed"})
    return ActionResult(EXIT_ALL_DONE, {})


def _handle_waiting() -> ActionResult:
    """Return waiting exit when no actionable tasks exist."""
    return ActionResult(EXIT_WAITING, {})


def _handle_dispatch_wave(action: Action, ctx: CycleContext) -> ActionResult:
    """Flip PENDING->IN_PROGRESS, dispatch workers, flip IN_PROGRESS->REVIEW."""
    dispatched: list[str] = []
    for task_id in action.tasks:
        if not ctx.task_lookup.get(task_id):
            logger.warning("Task info not found for %s, skipping", task_id)
            continue
        if _dispatch_single_worker(task_id, ctx):
            dispatched.append(task_id)
    output = {"action": "dispatch_wave", "tasks": dispatched, "detail": action.detail}
    return ActionResult(EXIT_ACTION_TAKEN, output)


def _dispatch_single_worker(task_id: str, ctx: CycleContext) -> bool:
    """Flip PENDING->IN_PROGRESS, run worker, flip to REVIEW or FAILED. Returns True on success."""
    info = ctx.task_lookup[task_id]
    if ctx.config.is_dry_run:
        logger.info("DRY-RUN: would dispatch worker for %s (%s)", task_id, info.dispatch_role)
        return True
    update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="IN_PROGRESS"))
    req = WorkerDispatchRequest(task_path=info.task_path, dispatch_role=info.dispatch_role)
    dispatch_result = dispatch_worker(req)
    if dispatch_result.exit_code != 0:
        logger.error("Worker failed for %s (exit %d)", task_id, dispatch_result.exit_code)
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="FAILED"))
        return False
    update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="REVIEW"))
    return True


def _handle_dispatch_advisor(action: Action, ctx: CycleContext) -> ActionResult:
    """Dispatch advisor for first REVIEW task; handle APPROVE/REVISE/BLOCKED."""
    task_id = action.tasks[0]
    if not ctx.task_lookup.get(task_id):
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [task_id], "detail": "Task info missing"})
    if ctx.config.is_dry_run:
        logger.info("DRY-RUN: would dispatch advisor for %s", task_id)
        output = {"action": "dispatch_advisor", "tasks": [task_id], "detail": action.detail}
        return ActionResult(EXIT_ACTION_TAKEN, output)
    return _run_advisor_cycle(task_id, ctx)


def _run_advisor_cycle(task_id: str, ctx: CycleContext) -> ActionResult:
    """Run advisor and process APPROVE/REVISE verdict."""
    info = ctx.task_lookup[task_id]
    req = AdvisorDispatchRequest(task_path=info.task_path)
    dispatch_result = dispatch_advisor(req)
    if dispatch_result.exit_code != 0:
        logger.error("Advisor dispatch failed for %s (exit %d)", task_id, dispatch_result.exit_code)
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [task_id], "detail": f"Advisor dispatch failed (exit {dispatch_result.exit_code})"})
    verdict = parse_advisor_output(dispatch_result.stdout)
    if verdict.is_approve:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="DONE"))
        output = {"action": "dispatch_advisor", "tasks": [task_id], "detail": "APPROVED"}
        return ActionResult(EXIT_ACTION_TAKEN, output)
    revise_ctx = ReviseContext(task_id=task_id, info=info, guidance=verdict.guidance)
    return _handle_revise(revise_ctx, ctx)


def _read_registers(task_path: str) -> str:
    """Read the Registers section text from a task file."""
    content = Path(task_path).read_text(encoding="utf-8")
    parts = content.split(REGISTERS_SECTION, 1)
    return parts[1].split("##", 1)[0] if len(parts) > 1 else ""


def _append_revise_entry(task_path: str, entry: str) -> None:
    """Append a REVISE entry line into the Registers section."""
    content = Path(task_path).read_text(encoding="utf-8")
    empty_marker = f"{REGISTERS_SECTION}\n— empty —"
    if empty_marker in content:
        updated = content.replace(empty_marker, f"{REGISTERS_SECTION}\n{entry}")
    else:
        reg_start = content.find(REGISTERS_SECTION)
        if reg_start < 0:
            updated = content
        else:
            after_header = reg_start + len(REGISTERS_SECTION)
            next_section = content.find("\n##", after_header)
            if next_section < 0:
                updated = content.rstrip() + "\n" + entry + "\n"
            else:
                updated = content[:next_section] + "\n" + entry + content[next_section:]
    Path(task_path).write_text(updated, encoding="utf-8")


def _flip_to_blocked(revise_ctx: ReviseContext, ctx: CycleContext) -> ActionResult:
    """Flip task to BLOCKED and return escalation result."""
    update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=revise_ctx.task_id, new_status="BLOCKED"))
    output = {"action": "escalate", "tasks": [revise_ctx.task_id], "detail": f"BLOCKED after {MAX_REVISE_ROUNDS} REVISE rounds"}
    return ActionResult(EXIT_BLOCKED, output)


def _run_revise_dispatch(revise_ctx: ReviseContext, ctx: CycleContext, round_count: int) -> ActionResult:
    """Record REVISE entry, dispatch worker, return result."""
    summary = revise_ctx.guidance[:GUIDANCE_SUMMARY_LIMIT] if revise_ctx.guidance else "advisor issues"
    entry_config = ReviseEntryConfig(round_number=round_count, nonce=NONCE_PLACEHOLDER, summary=summary)
    _append_revise_entry(revise_ctx.info.task_path, build_revise_register_entry(entry_config))
    revise_req = ReviseDispatchRequest(
        task_path=revise_ctx.info.task_path,
        guidance=revise_ctx.guidance,
        dispatch_role=revise_ctx.info.dispatch_role,
    )
    revise_result = dispatch_revise(revise_req)
    if revise_result.exit_code != 0:
        logger.error("REVISE dispatch failed for %s (exit %d)", revise_ctx.task_id, revise_result.exit_code)
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=revise_ctx.task_id, new_status="FAILED"))
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [revise_ctx.task_id], "detail": f"REVISE dispatch failed (exit {revise_result.exit_code})"})
    return ActionResult(EXIT_ACTION_TAKEN, {"action": "revise_worker", "tasks": [revise_ctx.task_id], "detail": f"REVISE round {round_count}"})


def _handle_revise(revise_ctx: ReviseContext, ctx: CycleContext) -> ActionResult:
    """Increment REVISE counter; re-dispatch or flip BLOCKED at max rounds."""
    registers = _read_registers(revise_ctx.info.task_path)
    round_count = count_revise_rounds(registers) + 1
    if round_count > MAX_REVISE_ROUNDS:
        return _flip_to_blocked(revise_ctx, ctx)
    return _run_revise_dispatch(revise_ctx, ctx, round_count)


if __name__ == "__main__":
    sys.exit(main())
