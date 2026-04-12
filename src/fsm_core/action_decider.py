"""Action decision logic for the orchestrator dispatch loop.

Given task statuses and dependencies, determines the next high-priority action.
Pure function with no I/O, no logging, no side effects.
"""

from dataclasses import dataclass


# Action outcome types (6-level priority cascade)
ESCALATE_BLOCKED = "escalate_blocked"
DISPATCH_ADVISOR = "dispatch_advisor"
DISPATCH_WAVE = "dispatch_wave"
WAVE_CHECKPOINT_PENDING = "wave_checkpoint_pending"
ALL_DONE = "all_done"
WAITING = "waiting"
ERROR_NO_TASKS = "error_no_tasks"


@dataclass(frozen=True)
class TaskStatus:
    """Snapshot of one task's state."""

    task_id: str
    status: str
    dispatch_role: str
    depends: list[str]
    wave: int = 0
    has_user_confirmation: bool = False


@dataclass(frozen=True)
class PipelineState:
    """Complete pipeline state at a point in time."""

    tasks: list[TaskStatus]


@dataclass(frozen=True)
class Action:
    """Decision outcome: what to do next."""

    kind: str
    tasks: list[str]
    detail: str


def _maybe_advisor_at_wave_gate(state: PipelineState, review: list[TaskStatus]) -> Action | None:
    """Dispatch advisor on the earliest-REVIEW wave only if that wave is fully gated."""
    earliest_wave = min(t.wave for t in review)
    wave_tasks = [t for t in state.tasks if t.wave == earliest_wave]
    if not all(t.status in ("DONE", "REVIEW") for t in wave_tasks):
        return None
    wave_review_ids = [t.task_id for t in review if t.wave == earliest_wave]
    detail = f"Wave {earliest_wave} gate reached — batch-advising {len(wave_review_ids)} tasks"
    return Action(DISPATCH_ADVISOR, wave_review_ids, detail)


def _find_wave_checkpoint(state: PipelineState) -> Action | None:
    """Return WAVE_CHECKPOINT_PENDING if a fully-DONE wave has a confirmation-required task."""
    by_wave: dict[int, list[TaskStatus]] = {}
    for task in state.tasks:
        by_wave.setdefault(task.wave, []).append(task)
    for wave in sorted(by_wave.keys()):
        action = _checkpoint_for_wave(wave, by_wave[wave])
        if action is not None:
            return action
    return None


def _checkpoint_for_wave(wave: int, tasks: list[TaskStatus]) -> Action | None:
    """Return a checkpoint Action for a single wave if it is DONE and confirmation-required."""
    if not all(t.status == "DONE" for t in tasks):
        return None
    if not any(t.has_user_confirmation for t in tasks):
        return None
    task_ids = [t.task_id for t in tasks]
    detail = f"Wave {wave} complete, requires confirmation before wave {wave + 1}"
    return Action(WAVE_CHECKPOINT_PENDING, task_ids, detail)


def _find_ready_tasks(state: PipelineState) -> list[str]:
    """Find all PENDING tasks with dependencies satisfied.

    A dep is satisfied if the predecessor is DONE, OR the predecessor is REVIEW
    AND belongs to the same wave as the candidate task. Intra-wave REVIEW satisfies
    deps because sub-task chains cascade freely within a wave — the advisor reviews
    the whole wave at the boundary. Cross-wave deps must be DONE.
    """
    by_id = {t.task_id: t for t in state.tasks}
    ready = []
    for task in state.tasks:
        if task.status != "PENDING":
            continue
        if _all_deps_satisfied(task, by_id):
            ready.append(task.task_id)
    return ready


def _all_deps_satisfied(task: TaskStatus, by_id: dict[str, TaskStatus]) -> bool:
    """Return True if every dep of task is DONE, or REVIEW in the same wave."""
    for dep_id in task.depends:
        dep = by_id.get(dep_id)
        if dep is None:
            return False
        if dep.status == "DONE":
            continue
        if dep.status == "REVIEW" and dep.wave == task.wave:
            continue
        return False
    return True


def decide_action(state: PipelineState) -> Action:
    """Determine the next action in a 7-level priority cascade."""
    if not state.tasks:
        return Action(ERROR_NO_TASKS, [], "No tasks found in pipeline")
    for check in _DECISION_CASCADE:
        action = check(state)
        if action is not None:
            return action
    return Action(WAITING, [], "All remaining tasks are IN_PROGRESS, REVIEW, or EXECUTING")


def _check_blocked(state: PipelineState) -> Action | None:
    """Priority 1: any BLOCKED task escalates."""
    blocked = [t for t in state.tasks if t.status == "BLOCKED"]
    if not blocked:
        return None
    ids = [t.task_id for t in blocked]
    return Action(ESCALATE_BLOCKED, ids, f"Found {len(blocked)} BLOCKED task(s)")


def _check_wave_advisor(state: PipelineState) -> Action | None:
    """Priority 2: earliest-REVIEW wave fully gated → dispatch advisor."""
    review = [t for t in state.tasks if t.status == "REVIEW"]
    if not review:
        return None
    return _maybe_advisor_at_wave_gate(state, review)


def _check_ready_wave(state: PipelineState) -> Action | None:
    """Priority 3: any PENDING task with satisfied deps → dispatch wave."""
    ready = _find_ready_tasks(state)
    if not ready:
        return None
    return Action(DISPATCH_WAVE, ready, f"Dispatching {len(ready)} ready task(s)")


def _check_all_done(state: PipelineState) -> Action | None:
    """Priority 5: every task is DONE → ALL_DONE."""
    if not all(t.status == "DONE" for t in state.tasks):
        return None
    return Action(ALL_DONE, [], "All tasks completed")


_DECISION_CASCADE = (_check_blocked, _check_wave_advisor, _find_wave_checkpoint, _check_ready_wave, _check_all_done)
