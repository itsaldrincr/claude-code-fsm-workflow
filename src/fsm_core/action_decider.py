"""Action decision logic for the orchestrator dispatch loop.

Given task statuses and dependencies, determines the next high-priority action.
Pure function with no I/O, no logging, no side effects.
"""

from dataclasses import dataclass


# Action outcome types (6-level priority cascade)
ESCALATE_BLOCKED = "escalate_blocked"
DISPATCH_ADVISOR = "dispatch_advisor"
DISPATCH_WAVE = "dispatch_wave"
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


def _find_ready_tasks(state: PipelineState) -> list[str]:
    """Find all PENDING tasks with all dependencies satisfied.

    Args:
        state: Current pipeline state.

    Returns:
        List of task IDs that are PENDING and have all deps DONE.
    """
    done_tasks = {t.task_id for t in state.tasks if t.status == "DONE"}
    ready = []
    for task in state.tasks:
        if task.status == "PENDING":
            all_deps_done = all(dep in done_tasks for dep in task.depends)
            if all_deps_done:
                ready.append(task.task_id)
    return ready


def decide_action(state: PipelineState) -> Action:
    """Determine the next action in priority order.

    Priority cascade (first match wins):
    1. Any BLOCKED -> escalate
    2. Any REVIEW -> dispatch advisor for first REVIEW
    3. Any PENDING with deps satisfied -> dispatch wave of all ready
    4. All DONE -> exit success
    5. Only IN_PROGRESS/REVIEW/EXECUTING -> wait
    6. No tasks -> error

    Args:
        state: Current pipeline state.

    Returns:
        Action describing what to do next.
    """
    if not state.tasks:
        return Action(ERROR_NO_TASKS, [], "No tasks found in pipeline")

    blocked = [t for t in state.tasks if t.status == "BLOCKED"]
    if blocked:
        return Action(
            ESCALATE_BLOCKED, [t.task_id for t in blocked], f"Found {len(blocked)} BLOCKED task(s)"
        )

    review = [t for t in state.tasks if t.status == "REVIEW"]
    if review:
        first_review = review[0].task_id
        return Action(DISPATCH_ADVISOR, [first_review], f"Advising on {first_review}")

    ready = _find_ready_tasks(state)
    if ready:
        return Action(DISPATCH_WAVE, ready, f"Dispatching {len(ready)} ready task(s)")

    is_all_done = all(t.status == "DONE" for t in state.tasks)
    if is_all_done:
        return Action(ALL_DONE, [], "All tasks completed")

    return Action(WAITING, [], "All remaining tasks are IN_PROGRESS, REVIEW, or EXECUTING")
