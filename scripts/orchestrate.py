"""CLI entry point that wires all fsm_core modules into a single dispatch cycle."""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src import config as app_config
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
from src.fsm_core.auto_heal import heal_stale_in_progress
from src.fsm_core.claude_session_backend import (
    enqueue_advisor_intent,
    enqueue_worker_intents,
    mark_result_applied,
    read_pending_results,
)
from src.fsm_core.startup_checks import (
    find_state_drifts,
    resolve_dispatch_mode,
    sync_task_states_to_map,
)
from src.fsm_core.dispatch_contract import (
    AdvisorDispatchRequest,
    WorkerDispatchRequest,
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
BUG_SCANNER_PAIR_SIZE: int = 2
DISPATCH_LINE_RE: re.Pattern[str] = re.compile(r"^dispatch:\s*.+$", re.MULTILINE)
SIMPLE_FIX_HINTS: tuple[str, ...] = (
    "lint",
    "format",
    "style",
    "typing",
    "type hint",
    "import",
    "unused",
    "discipline",
)


@dataclass
class OrchestrateConfig:
    """Configuration for a single orchestration cycle."""

    workspace: Path
    is_dry_run: bool
    dispatch_mode: str = app_config.DISPATCH_MODE
    sync_task_state_to_map: bool = False
    strict_map_task_state: bool = False


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
    dispatch_mode = resolve_dispatch_mode(args.dispatch_mode)
    config = OrchestrateConfig(
        workspace=Path(args.workspace),
        is_dry_run=args.dry_run,
        dispatch_mode=dispatch_mode,
        sync_task_state_to_map=args.sync_task_state_to_map,
        strict_map_task_state=args.strict_map_task_state,
    )
    try:
        _run_startup_checks(config)
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
    parser.add_argument(
        "--dispatch-mode",
        default=app_config.DISPATCH_MODE,
        help="Dispatch backend mode: claude_session",
    )
    parser.add_argument(
        "--sync-task-state-to-map",
        action="store_true",
        help="Fix task frontmatter state fields to match MAP.md before dispatch.",
    )
    parser.add_argument(
        "--strict-map-task-state",
        action="store_true",
        help="Exit with error if any MAP.md/task frontmatter state drift is detected.",
    )
    return parser.parse_args()


def _run_startup_checks(config: OrchestrateConfig) -> None:
    """Run startup preflight and reconciliation checks."""
    map_path = config.workspace / "MAP.md"
    if not map_path.exists():
        return
    healed = heal_stale_in_progress(config.workspace)
    for task_id in healed:
        logger.warning("Auto-healed stale IN_PROGRESS task: %s", task_id)
    drifts = find_state_drifts(config.workspace, map_path)
    if drifts and config.sync_task_state_to_map:
        changed = sync_task_states_to_map(drifts)
        logger.warning("Synced %d task file state field(s) to MAP.md statuses.", changed)
        drifts = find_state_drifts(config.workspace, map_path)
    if not drifts:
        return
    for drift in drifts:
        logger.warning(
            "State drift: %s MAP=%s task=%s (%s)",
            drift.task_id,
            drift.map_status,
            drift.task_state,
            drift.task_path,
        )
    if config.strict_map_task_state:
        raise RuntimeError("MAP/task state drift detected. Re-run with --sync-task-state-to-map.")


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


def _restore_unflagged_to_review(wave_task_ids: list[str], targets: set[str], ctx: CycleContext) -> None:
    """Move non-targeted EXECUTING tasks back to REVIEW after wave-gate REVISE."""
    for task_id in wave_task_ids:
        if task_id in targets:
            continue
        info = ctx.task_lookup.get(task_id)
        if info is None:
            continue
        if info.status == "EXECUTING":
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="REVIEW"))


def _apply_worker_result(result_task_path: str, exit_code: int, ctx: CycleContext) -> bool:
    """Apply one worker result to MAP.md. Returns True if matched/applied."""
    path_to_id = {
        str(Path(info.task_path).resolve()): info.task_id
        for info in ctx.task_lookup.values()
        if info.status == "IN_PROGRESS"
    }
    task_id = path_to_id.get(str(Path(result_task_path).resolve()))
    if task_id is None:
        return False
    status = "REVIEW" if exit_code == 0 else "FAILED"
    update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status=status))
    return True


def _apply_advisor_result(task_paths: tuple[str, ...], exit_code: int, stdout: str, ctx: CycleContext) -> bool:
    """Apply one legacy single-reviewer result to MAP.md. Returns True if matched/applied."""
    ids_by_path = {str(Path(info.task_path).resolve()): info.task_id for info in ctx.task_lookup.values()}
    wave_task_ids: list[str] = []
    for path in task_paths:
        task_id = ids_by_path.get(str(Path(path).resolve()))
        if task_id is None:
            return False
        wave_task_ids.append(task_id)
    if exit_code != 0:
        for task_id in wave_task_ids:
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="REVIEW"))
        return True
    verdict = parse_advisor_output(stdout)
    if verdict.is_approve:
        for task_id in wave_task_ids:
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="DONE"))
        return True
    revise_ctx = WaveReviseContext(wave_task_ids=wave_task_ids, guidance=verdict.guidance)
    flagged = extract_flagged_task_ids(revise_ctx.guidance, revise_ctx.wave_task_ids)
    targets = set(flagged if flagged else revise_ctx.wave_task_ids)
    _restore_unflagged_to_review(revise_ctx.wave_task_ids, targets, ctx)
    _revise_wave_batch(revise_ctx, ctx)
    return True


def _apply_bug_scanner_pair_results(results: list, ctx: CycleContext) -> bool:
    """Apply one completed bug-scanner pair result group to MAP.md."""
    ids_by_path = {str(Path(info.task_path).resolve()): info.task_id for info in ctx.task_lookup.values()}
    wave_task_ids: list[str] = []
    for result in results:
        for path in result.task_paths:
            task_id = ids_by_path.get(str(Path(path).resolve()))
            if task_id is None:
                return False
            if task_id not in wave_task_ids:
                wave_task_ids.append(task_id)
    if any(result.exit_code != 0 for result in results):
        for task_id in wave_task_ids:
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="REVIEW"))
        return True
    verdicts = [parse_advisor_output(result.stdout) for result in results]
    if all(verdict.is_approve for verdict in verdicts):
        for task_id in wave_task_ids:
            update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="DONE"))
        return True
    guidance_parts = [verdict.guidance for verdict in verdicts if not verdict.is_approve and verdict.guidance]
    combined_guidance = "\n\n".join(guidance_parts).strip() or "bug-scanner issues"
    flagged: set[str] = set()
    for verdict in verdicts:
        if verdict.is_approve:
            continue
        flagged.update(extract_flagged_task_ids(verdict.guidance, wave_task_ids))
    targets = flagged if flagged else set(wave_task_ids)
    _restore_unflagged_to_review(wave_task_ids, targets, ctx)
    _revise_wave_batch(WaveReviseContext(wave_task_ids=wave_task_ids, guidance=combined_guidance), ctx)
    return True


def _apply_pending_claude_session_results(config: OrchestrateConfig, map_path: Path, tasks: list[TaskInfo]) -> int:
    """Apply pending .fsm-results envelopes into MAP state transitions."""
    if config.is_dry_run:
        return 0
    ctx = CycleContext(config=config, map_path=map_path, task_lookup={t.task_id: t for t in tasks})
    applied = 0
    pending_results = read_pending_results(config.workspace)
    pair_groups: dict[str, list] = {}
    for result in pending_results:
        matched = False
        if result.kind in ("worker", "revise"):
            matched = _apply_worker_result(result.task_path, result.exit_code, ctx)
            if matched:
                mark_result_applied(config.workspace, result.result_path)
                applied += 1
            continue
        if result.kind != "advisor":
            continue
        if result.pair_key:
            pair_groups.setdefault(result.pair_key, []).append(result)
            continue
        matched = _apply_advisor_result(result.task_paths, result.exit_code, result.stdout, ctx)
        if matched:
            mark_result_applied(config.workspace, result.result_path)
            applied += 1
    for grouped in pair_groups.values():
        expected = max(result.scanner_total for result in grouped)
        if len(grouped) < expected:
            continue
        selected = sorted(grouped, key=lambda item: item.scanner_index)[:expected]
        if not _apply_bug_scanner_pair_results(selected, ctx):
            continue
        for result in selected:
            mark_result_applied(config.workspace, result.result_path)
            applied += 1
    return applied


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
    applied_results = _apply_pending_claude_session_results(config, map_path, tasks)
    if applied_results > 0:
        logger.info("Applied %d claude_session result envelope(s).", applied_results)
        tasks = read_task_dispatch_info(request)
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
    detail = f"{', '.join(action.tasks)} BLOCKED after {MAX_REVISE_ROUNDS} bug-scanner REVISE rounds"
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
    """Flip PENDING->IN_PROGRESS for ready tasks and enqueue claude_session intents."""
    valid_ids = [tid for tid in action.tasks if ctx.task_lookup.get(tid)]
    if ctx.config.is_dry_run:
        return _dry_run_wave(valid_ids, action.detail)
    for tid in valid_ids:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=tid, new_status="IN_PROGRESS"))
    requests = [_build_worker_request(tid, ctx) for tid in valid_ids]
    intents = enqueue_worker_intents(ctx.config.workspace, requests)
    output = {
        "action": "dispatch_wave",
        "tasks": valid_ids,
        "detail": f"Queued {len(intents)} worker intent(s) for claude_session dispatch",
    }
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


def _split_bug_scanner_shards(task_paths: list[str]) -> tuple[list[str], list[str]]:
    """Split wave task paths into two deterministic scanner shards."""
    unique = sorted({str(Path(path).resolve()) for path in task_paths})
    if len(unique) < 2:
        single = unique if unique else task_paths
        return list(single), list(single)
    left = [path for idx, path in enumerate(unique) if idx % 2 == 0]
    right = [path for idx, path in enumerate(unique) if idx % 2 == 1]
    return left, right


def _build_pair_key(task_ids: list[str]) -> str:
    """Build stable key used to correlate bug-scanner pair result envelopes."""
    stable = ",".join(sorted(task_ids))
    return f"pair:{stable}"


def _handle_dispatch_advisor(action: Action, ctx: CycleContext) -> ActionResult:
    """Dispatch bug-scanner pair for the whole wave batch."""
    wave_task_ids = action.tasks
    missing = [tid for tid in wave_task_ids if not ctx.task_lookup.get(tid)]
    if missing:
        return ActionResult(EXIT_ERROR, {"action": "error", "tasks": missing, "detail": "Task info missing"})
    if ctx.config.is_dry_run:
        logger.info("DRY-RUN: would dispatch bug-scanner pair for wave batch %s", wave_task_ids)
        output = {"action": "dispatch_advisor", "tasks": wave_task_ids, "detail": action.detail}
        return ActionResult(EXIT_ACTION_TAKEN, output)
    for task_id in wave_task_ids:
        update_map_status(StatusUpdateRequest(map_path=ctx.map_path, task_id=task_id, new_status="EXECUTING"))
    task_paths = [ctx.task_lookup[tid].task_path for tid in wave_task_ids]
    shard_left, shard_right = _split_bug_scanner_shards(task_paths)
    pair_key = _build_pair_key(wave_task_ids)
    intents = [
        enqueue_advisor_intent(
            ctx.config.workspace,
            AdvisorDispatchRequest(task_paths=shard_left),
            pair_key=pair_key,
            scanner_index=0,
            scanner_total=BUG_SCANNER_PAIR_SIZE,
        ),
        enqueue_advisor_intent(
            ctx.config.workspace,
            AdvisorDispatchRequest(task_paths=shard_right),
            pair_key=pair_key,
            scanner_index=1,
            scanner_total=BUG_SCANNER_PAIR_SIZE,
        ),
    ]
    detail = f"Queued {len(intents)} bug-scanner intents for {len(wave_task_ids)} task(s)"
    return ActionResult(EXIT_ACTION_TAKEN, {"action": "dispatch_advisor", "tasks": wave_task_ids, "detail": detail})


@dataclass(frozen=True)
class WaveReviseContext:
    """Bundled context for a wave-batch REVISE decision."""

    wave_task_ids: list[str]
    guidance: str


def _revise_wave_batch(rctx: WaveReviseContext, ctx: CycleContext) -> ActionResult:
    """Re-dispatch flagged tasks from a wave-batch REVISE verdict.

    Parses bug-scanner guidance for task_ids; each flagged task gets a REVISE round
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
    summary = request.guidance[:GUIDANCE_SUMMARY_LIMIT] if request.guidance else "bug-scanner issues"
    entry_config = ReviseEntryConfig(round_number=round_count, nonce=NONCE_PLACEHOLDER, summary=summary)
    _append_revise_entry(info.task_path, build_revise_register_entry(entry_config))
    repair_role = _select_repair_role(info.dispatch_role, request.guidance)
    _rewrite_dispatch_role(info.task_path, repair_role)
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


def _select_repair_role(dispatch_role: str, guidance: str) -> str:
    """Route REVISE work to code-fixer for simple fixes, debugger otherwise."""
    if dispatch_role == "fsm-integrator":
        return "debugger"
    lowered = guidance.lower()
    if any(hint in lowered for hint in SIMPLE_FIX_HINTS):
        return "code-fixer"
    return "debugger"


def _rewrite_dispatch_role(task_path: str, dispatch_role: str) -> None:
    """Set task frontmatter dispatch role for the next re-dispatch cycle."""
    content = Path(task_path).read_text(encoding="utf-8")
    updated = DISPATCH_LINE_RE.sub(f"dispatch: {dispatch_role}", content, count=1)
    if updated == content:
        return
    Path(task_path).write_text(updated, encoding="utf-8")




if __name__ == "__main__":
    sys.exit(main())
