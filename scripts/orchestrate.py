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
    WAVE_CHECKPOINT_PENDING,
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
    extract_flagged_task_ids,
    parse_advisor_output,
)
from src.fsm_core.map_io import StatusUpdateRequest, update_map_status
from src.fsm_core.map_lock import LockTimeoutError, map_lock
from src.fsm_core.map_reader import ReadTasksRequest, TaskInfo, read_task_dispatch_info
from src.fsm_core.session_state import read_state
from src.fsm_core.subprocess_dispatch import (
    AdvisorDispatchRequest,
    DispatchResult,
    WorkerDispatchRequest,
    dispatch_advisor,
    dispatch_workers_parallel,
)

logger = logging.getLogger(__name__)

EXIT_ALL_DONE: int = 0
EXIT_ACTION_TAKEN: int = 1
EXIT_WAITING: int = 2
EXIT_BLOCKED: int = 3
EXIT_ERROR: int = 4
EXIT_AUDIT_FAILED: int = 5

AUDIT_SENTINEL: str = ".audit_clean"
CHECKPOINT_SENTINEL: str = ".checkpoint_pending"
REGISTERS_SECTION: str = "## Registers"
NONCE_PLACEHOLDER: str = "000000"
GUIDANCE_SUMMARY_LIMIT: int = 2000
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


@dataclass(frozen=True)
class CheckpointPayload:
    """Payload written to the checkpoint sentinel file at a wave gate."""

    workspace: Path
    wave: int
    triggering_tasks: list[str]
    next_wave: int
    summary: str


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
            wave=t.wave,
        )
        for t in tasks
    ]
    return PipelineState(tasks=statuses)


def _should_skip_dispatch(workspace: Path) -> bool:
    """Return True if dispatch should be skipped due to checkpoint or paused session."""
    if _has_checkpoint_sentinel(workspace):
        return True
    session_state = read_state(workspace)
    if session_state is None:
        return False
    if session_state.status == "paused":
        return True
    return session_state.checkpoints_skipped_this_session


def _run_cycle(config: OrchestrateConfig) -> ActionResult:
    """Read pipeline state, decide action, execute it, return result."""
    map_path = config.workspace / "MAP.md"
    if not map_path.exists():
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": "MAP.md not found"})
    if _should_skip_dispatch(config.workspace):
        return ActionResult(EXIT_WAITING, {"action": "waiting", "tasks": [], "detail": "dispatch skipped"})
    try:
        request = ReadTasksRequest(workspace=config.workspace, map_path=map_path)
        tasks = read_task_dispatch_info(request)
    except (FileNotFoundError, LockTimeoutError) as exc:
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": [], "detail": str(exc)})
    state = _build_pipeline_state(tasks)
    action = decide_action(state)
    if _should_skip_dispatch(config.workspace):
        return ActionResult(EXIT_WAITING, {"action": "waiting", "tasks": [], "detail": "dispatch skipped (re-check)"})
    ctx = CycleContext(config=config, map_path=map_path, task_lookup={t.task_id: t for t in tasks})
    return _dispatch_action(action, ctx)


def _extract_wave_number(action: Action, ctx: CycleContext) -> int:
    """Return wave number from the first task in action, or 0 if not found."""
    if action.tasks:
        info = ctx.task_lookup.get(action.tasks[0])
        if info:
            return info.wave
    return 0


def _handle_wave_checkpoint(action: Action, ctx: CycleContext) -> ActionResult:
    """Write checkpoint sentinel under map_lock and return EXIT_WAITING."""
    workspace = ctx.config.workspace
    wave_num = _extract_wave_number(action, ctx)
    payload = CheckpointPayload(
        workspace=workspace,
        wave=wave_num,
        triggering_tasks=action.tasks,
        next_wave=wave_num + 1,
        summary=action.detail,
    )
    with map_lock(ctx.map_path):
        _write_checkpoint_sentinel(payload)
    return ActionResult(EXIT_WAITING, {"action": "wave_checkpoint", "tasks": action.tasks, "detail": action.detail})


def _dispatch_action(action: Action, ctx: CycleContext) -> ActionResult:
    """Route action to the appropriate handler."""
    if action.kind == ESCALATE_BLOCKED:
        return _handle_escalate(action)
    if action.kind == DISPATCH_ADVISOR:
        return _handle_dispatch_advisor(action, ctx)
    if action.kind == DISPATCH_WAVE:
        return _handle_dispatch_wave(action, ctx)
    if action.kind == WAVE_CHECKPOINT_PENDING:
        return _handle_wave_checkpoint(action, ctx)
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


def _has_checkpoint_sentinel(workspace: Path) -> bool:
    """Return True if the checkpoint sentinel file exists in workspace."""
    return (workspace / CHECKPOINT_SENTINEL).exists()


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


def _serialize_checkpoint(payload: CheckpointPayload) -> str:
    """Serialize a CheckpointPayload to JSON string."""
    data = {
        "wave": payload.wave,
        "triggering_tasks": payload.triggering_tasks,
        "next_wave": payload.next_wave,
        "summary": payload.summary,
    }
    return json.dumps(data, indent=2)


def _write_checkpoint_sentinel(payload: CheckpointPayload) -> None:
    """Write checkpoint sentinel JSON to workspace."""
    sentinel_path = payload.workspace / CHECKPOINT_SENTINEL
    sentinel_path.write_text(_serialize_checkpoint(payload), encoding="utf-8")


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
    """Flip PENDING->IN_PROGRESS for all ready tasks, dispatch them IN PARALLEL,
    then flip each to REVIEW or FAILED based on its exit code.

    True wall-clock parallelism: ThreadPoolExecutor launches N workers at once,
    each running its own `claude -p` subprocess. Cap: MAX_PARALLEL_WORKERS (8).
    """
    valid_ids = [tid for tid in action.tasks if ctx.task_lookup.get(tid)]
    if ctx.config.is_dry_run:
        return _dry_run_wave(valid_ids, action.detail)
    for tid in valid_ids:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=tid, new_status="IN_PROGRESS"))
    requests = [_build_worker_request(tid, ctx) for tid in valid_ids]
    results = dispatch_workers_parallel(requests)
    outcomes = list(zip(valid_ids, results))
    dispatched = _process_parallel_results(outcomes, ctx)
    output = {"action": "dispatch_wave", "tasks": dispatched, "detail": action.detail}
    return ActionResult(EXIT_ACTION_TAKEN, output)


def _dry_run_wave(task_ids: list[str], detail: str) -> ActionResult:
    """DRY-RUN path: log what would be dispatched without spawning workers."""
    for tid in task_ids:
        logger.info("DRY-RUN: would dispatch worker for %s", tid)
    return ActionResult(EXIT_ACTION_TAKEN, {"action": "dispatch_wave", "tasks": task_ids, "detail": detail})


def _build_worker_request(task_id: str, ctx: CycleContext) -> WorkerDispatchRequest:
    """Construct a WorkerDispatchRequest from a task_id + context lookup."""
    info = ctx.task_lookup[task_id]
    return WorkerDispatchRequest(task_path=info.task_path, dispatch_role=info.dispatch_role)


def _process_parallel_results(outcomes: list[tuple[str, DispatchResult]], ctx: CycleContext) -> list[str]:
    """Flip each task to REVIEW (on exit 0) or FAILED (non-zero). Returns REVIEW-flipped IDs."""
    dispatched: list[str] = []
    for task_id, result in outcomes:
        if result.exit_code == 0:
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="REVIEW"))
            dispatched.append(task_id)
        else:
            logger.error("Worker failed for %s (exit %d)", task_id, result.exit_code)
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="FAILED"))
    return dispatched


def _handle_dispatch_advisor(action: Action, ctx: CycleContext) -> ActionResult:
    """Dispatch advisor for the whole wave batch; handle APPROVE/REVISE/BLOCKED."""
    wave_task_ids = action.tasks
    missing = [tid for tid in wave_task_ids if not ctx.task_lookup.get(tid)]
    if missing:
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": missing, "detail": "Task info missing"})
    if ctx.config.is_dry_run:
        logger.info("DRY-RUN: would dispatch advisor for wave batch %s", wave_task_ids)
        output = {"action": "dispatch_advisor", "tasks": wave_task_ids, "detail": action.detail}
        return ActionResult(EXIT_ACTION_TAKEN, output)
    return _run_advisor_cycle(wave_task_ids, ctx)


def _run_advisor_cycle(wave_task_ids: list[str], ctx: CycleContext) -> ActionResult:
    """Run wave-batch advisor and process APPROVE/REVISE verdict."""
    task_paths = [ctx.task_lookup[tid].task_path for tid in wave_task_ids]
    req = AdvisorDispatchRequest(task_paths=task_paths)
    dispatch_result = dispatch_advisor(req)
    if dispatch_result.exit_code != 0:
        logger.error("Advisor dispatch failed for wave batch %s (exit %d)", wave_task_ids, dispatch_result.exit_code)
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": wave_task_ids, "detail": f"Advisor dispatch failed (exit {dispatch_result.exit_code})"})
    verdict = parse_advisor_output(dispatch_result.stdout)
    if verdict.is_approve:
        return _approve_wave_batch(wave_task_ids, ctx)
    return _revise_wave_batch(WaveReviseContext(wave_task_ids=wave_task_ids, guidance=verdict.guidance), ctx)


def _approve_wave_batch(wave_task_ids: list[str], ctx: CycleContext) -> ActionResult:
    """Flip every REVIEW task in the wave to DONE after advisor APPROVE."""
    for tid in wave_task_ids:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=tid, new_status="DONE"))
    output = {"action": "dispatch_advisor", "tasks": wave_task_ids, "detail": f"APPROVED wave batch ({len(wave_task_ids)} tasks)"}
    return ActionResult(EXIT_ACTION_TAKEN, output)


@dataclass(frozen=True)
class WaveReviseContext:
    """Bundled context for a wave-batch REVISE decision."""

    wave_task_ids: list[str]
    guidance: str


def _revise_wave_batch(rctx: WaveReviseContext, ctx: CycleContext) -> ActionResult:
    """Re-dispatch flagged tasks from a wave-batch REVISE verdict.

    Parses advisor guidance for task_ids; each flagged task gets a REVISE round
    note + flipped REVIEW -> PENDING. If a flagged task has already hit
    MAX_REVISE_ROUNDS, it escalates to BLOCKED.
    """
    flagged = extract_flagged_task_ids(rctx.guidance, rctx.wave_task_ids)
    targets = flagged if flagged else rctx.wave_task_ids
    blocked_result: ActionResult | None = None
    for tid in targets:
        result = _flag_one_for_revise(FlagOneRequest(tid=tid, guidance=rctx.guidance), ctx)
        if result is not None and blocked_result is None:
            blocked_result = result
    if blocked_result is not None:
        return blocked_result
    return _build_revise_result(targets)


@dataclass(frozen=True)
class FlagOneRequest:
    """Bundled (task_id, guidance) for a single-task REVISE flip."""

    tid: str
    guidance: str


def _flag_one_for_revise(request: FlagOneRequest, ctx: CycleContext) -> ActionResult | None:
    """Append REVISE note + flip PENDING. Returns BLOCKED ActionResult if over limit."""
    info = ctx.task_lookup[request.tid]
    round_count = count_revise_rounds(_read_registers(info.task_path)) + 1
    if round_count > MAX_REVISE_ROUNDS:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=request.tid, new_status="BLOCKED"))
        output = {"action": "escalate", "tasks": [request.tid], "detail": f"BLOCKED after {MAX_REVISE_ROUNDS} REVISE rounds"}
        return ActionResult(EXIT_BLOCKED, output)
    summary = request.guidance[:GUIDANCE_SUMMARY_LIMIT] if request.guidance else "advisor issues"
    entry_config = ReviseEntryConfig(round_number=round_count, nonce=NONCE_PLACEHOLDER, summary=summary)
    _append_revise_entry(info.task_path, build_revise_register_entry(entry_config))
    update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=request.tid, new_status="PENDING"))
    return None


def _build_revise_result(targets: list[str]) -> ActionResult:
    """Build the ActionResult wrapper for a successful wave-revise flip batch."""
    output = {
        "action": "revise_wave_batch",
        "tasks": targets,
        "detail": f"Flagged {len(targets)} task(s) for REVISE; flipped REVIEW -> PENDING",
    }
    return ActionResult(EXIT_ACTION_TAKEN, output)


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




if __name__ == "__main__":
    sys.exit(main())
