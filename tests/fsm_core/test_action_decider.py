"""Tests for action_decider decision logic."""

import pytest

from src.fsm_core.action_decider import (
    ALL_DONE,
    DISPATCH_ADVISOR,
    DISPATCH_WAVE,
    ERROR_NO_TASKS,
    ESCALATE_BLOCKED,
    WAITING,
    WAVE_CHECKPOINT_PENDING,
    Action,
    PipelineState,
    TaskStatus,
    decide_action,
)


class TestDecideActionBlockedPriority:
    """Test BLOCKED has highest priority."""

    def test_blocked_over_review(self) -> None:
        """BLOCKED should escalate even if REVIEW tasks exist."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "BLOCKED", "fsm-executor", []),
                TaskStatus("t2", "REVIEW", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == ESCALATE_BLOCKED
        assert "t1" in action.tasks

    def test_blocked_over_pending(self) -> None:
        """BLOCKED should escalate over ready PENDING tasks."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "BLOCKED", "fsm-executor", []),
                TaskStatus("t2", "PENDING", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == ESCALATE_BLOCKED
        assert action.tasks == ["t1"]


class TestDecideActionReviewPriority:
    """Test REVIEW comes after BLOCKED."""

    def test_review_single_task(self) -> None:
        """Single REVIEW task should dispatch advisor."""
        state = PipelineState(
            tasks=[TaskStatus("t1", "REVIEW", "fsm-executor", [])]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_ADVISOR
        assert action.tasks == ["t1"]

    def test_review_first_only(self) -> None:
        """Batch-advise on all REVIEW tasks in the same wave."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "REVIEW", "fsm-executor", []),
                TaskStatus("t2", "REVIEW", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_ADVISOR
        assert set(action.tasks) == {"t1", "t2"}

    def test_review_over_pending_ready(self) -> None:
        """REVIEW in wave 1 takes priority over ready PENDING in wave 2."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "REVIEW", "fsm-executor", [], wave=1),
                TaskStatus("t2", "PENDING", "fsm-executor", [], wave=2),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_ADVISOR
        assert action.tasks == ["t1"]


class TestDecideActionPendingReady:
    """Test PENDING with satisfied dependencies."""

    def test_single_pending_no_deps(self) -> None:
        """Single PENDING with no deps should dispatch."""
        state = PipelineState(tasks=[TaskStatus("t1", "PENDING", "fsm-executor", [])])
        action = decide_action(state)
        assert action.kind == DISPATCH_WAVE
        assert action.tasks == ["t1"]

    def test_multiple_pending_no_deps(self) -> None:
        """Multiple ready PENDING should dispatch as one wave."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "PENDING", "fsm-executor", []),
                TaskStatus("t2", "PENDING", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_WAVE
        assert set(action.tasks) == {"t1", "t2"}

    def test_pending_with_satisfied_deps(self) -> None:
        """PENDING task with all deps DONE should be included."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", []),
                TaskStatus("t2", "PENDING", "fsm-executor", ["t1"]),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_WAVE
        assert action.tasks == ["t2"]

    def test_pending_with_unsatisfied_deps_excluded(self) -> None:
        """PENDING task with unsatisfied deps should not be included."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "IN_PROGRESS", "fsm-executor", []),
                TaskStatus("t2", "PENDING", "fsm-executor", ["t1"]),
            ]
        )
        action = decide_action(state)
        assert action.kind == WAITING

    def test_mixed_pending_some_ready(self) -> None:
        """Only tasks with satisfied deps should be dispatched."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", []),
                TaskStatus("t2", "PENDING", "fsm-executor", ["t1"]),
                TaskStatus("t3", "IN_PROGRESS", "fsm-executor", []),
                TaskStatus("t4", "PENDING", "fsm-executor", ["t3"]),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_WAVE
        assert action.tasks == ["t2"]

    def test_chain_dependencies_all_done(self) -> None:
        """Task depending on chain of DONE tasks should be ready."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", []),
                TaskStatus("t2", "DONE", "fsm-executor", ["t1"]),
                TaskStatus("t3", "PENDING", "fsm-executor", ["t2"]),
            ]
        )
        action = decide_action(state)
        assert action.kind == DISPATCH_WAVE
        assert action.tasks == ["t3"]


class TestDecideActionAllDone:
    """Test exit condition when all tasks are DONE."""

    def test_single_done(self) -> None:
        """Single DONE task should signal completion."""
        state = PipelineState(tasks=[TaskStatus("t1", "DONE", "fsm-executor", [])])
        action = decide_action(state)
        assert action.kind == ALL_DONE
        assert action.tasks == []

    def test_multiple_done(self) -> None:
        """All DONE tasks should signal completion."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", []),
                TaskStatus("t2", "DONE", "fsm-executor", ["t1"]),
            ]
        )
        action = decide_action(state)
        assert action.kind == ALL_DONE


class TestDecideActionWaiting:
    """Test waiting state for in-flight tasks."""

    def test_single_in_progress(self) -> None:
        """Single IN_PROGRESS task should trigger wait."""
        state = PipelineState(tasks=[TaskStatus("t1", "IN_PROGRESS", "fsm-executor", [])])
        action = decide_action(state)
        assert action.kind == WAITING

    def test_multiple_in_progress(self) -> None:
        """Multiple IN_PROGRESS should trigger wait."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "IN_PROGRESS", "fsm-executor", []),
                TaskStatus("t2", "IN_PROGRESS", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == WAITING

    def test_executing_tasks(self) -> None:
        """EXECUTING tasks should trigger wait."""
        state = PipelineState(tasks=[TaskStatus("t1", "EXECUTING", "fsm-executor", [])])
        action = decide_action(state)
        assert action.kind == WAITING

    def test_mixed_in_flight_statuses(self) -> None:
        """Mix of IN_PROGRESS and EXECUTING should trigger wait."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "IN_PROGRESS", "fsm-executor", []),
                TaskStatus("t2", "EXECUTING", "fsm-executor", []),
            ]
        )
        action = decide_action(state)
        assert action.kind == WAITING


class TestDecideActionError:
    """Test error conditions."""

    def test_no_tasks(self) -> None:
        """Empty task list should return error."""
        state = PipelineState(tasks=[])
        action = decide_action(state)
        assert action.kind == ERROR_NO_TASKS
        assert action.tasks == []


class TestActionDataclass:
    """Test Action dataclass immutability and structure."""

    def test_action_is_frozen(self) -> None:
        """Action should be immutable."""
        action = Action(DISPATCH_WAVE, ["t1"], "test")
        with pytest.raises(AttributeError):
            action.kind = "other"

    def test_action_fields(self) -> None:
        """Action should have required fields."""
        action = Action("some_kind", ["t1", "t2"], "detail text")
        assert action.kind == "some_kind"
        assert action.tasks == ["t1", "t2"]
        assert action.detail == "detail text"


class TestPipelineStateDataclass:
    """Test PipelineState immutability."""

    def test_pipeline_state_is_frozen(self) -> None:
        """PipelineState should be immutable."""
        tasks = [TaskStatus("t1", "PENDING", "fsm-executor", [])]
        state = PipelineState(tasks=tasks)
        with pytest.raises(AttributeError):
            state.tasks = []


class TestTaskStatusDataclass:
    """Test TaskStatus immutability."""

    def test_task_status_is_frozen(self) -> None:
        """TaskStatus should be immutable."""
        task = TaskStatus("t1", "PENDING", "fsm-executor", [])
        with pytest.raises(AttributeError):
            task.task_id = "other"


class TestWaveCheckpointPending:
    """Test WAVE_CHECKPOINT_PENDING detection."""

    def test_single_wave_flag_triggers_checkpoint(self) -> None:
        """Wave with has_user_confirmation=True triggers checkpoint when complete."""
        state = PipelineState(
            tasks=[
                TaskStatus(
                    "t1",
                    "DONE",
                    "fsm-executor",
                    [],
                    wave=1,
                    has_user_confirmation=True,
                ),
            ]
        )
        action = decide_action(state)
        assert action.kind == WAVE_CHECKPOINT_PENDING
        assert action.tasks == ["t1"]

    def test_multi_wave_cascade(self) -> None:
        """Wave 1 without flag completes normally; wave 2 flag triggers checkpoint."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", [], wave=1, has_user_confirmation=False),
                TaskStatus(
                    "t2",
                    "DONE",
                    "fsm-executor",
                    [],
                    wave=2,
                    has_user_confirmation=True,
                ),
            ]
        )
        action = decide_action(state)
        assert action.kind == WAVE_CHECKPOINT_PENDING
        assert action.tasks == ["t2"]

    def test_no_checkpoint_when_not_required(self) -> None:
        """All DONE without has_user_confirmation cascades to ALL_DONE."""
        state = PipelineState(
            tasks=[
                TaskStatus("t1", "DONE", "fsm-executor", [], wave=1, has_user_confirmation=False),
            ]
        )
        action = decide_action(state)
        assert action.kind == ALL_DONE
        assert action.tasks == []
