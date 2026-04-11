"""End-to-end tests for scripts/orchestrate.py with mocked subprocess."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.orchestrate import (
    EXIT_ACTION_TAKEN,
    EXIT_ALL_DONE,
    EXIT_AUDIT_FAILED,
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_WAITING,
    AuditGateResult,
    CycleContext,
    OrchestrateConfig,
    _handle_all_done,
    _handle_escalate,
    _handle_waiting,
    _run_cycle,
)
from src.fsm_core.action_decider import Action, ESCALATE_BLOCKED


# ---- Fixtures ----

MAP_PENDING: str = """\
# MAP

## Active Tasks

### Wave 1
Project/
  src/engine/  [task_001_foo.md] ........ PENDING
"""

MAP_REVIEW: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ REVIEW
"""

MAP_ALL_DONE: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ DONE
"""

MAP_BLOCKED: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ BLOCKED
"""

MAP_IN_PROGRESS: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ IN_PROGRESS
"""

TASK_FRONTMATTER: str = """\
---
id: task_001
name: foo
state: PENDING
step: 0 of 1
depends: []
wave: 1
dispatch: fsm-executor
checkpoint: aabbcc
created: 2026-01-01
---

## Files
Creates:
  foo.py

## Program
1. Do something

## Registers
— empty —

## Working Memory
— empty —

## Acceptance Criteria
- [ ] It works
"""


@dataclass
class _WorkspaceFixture:
    workspace: Path
    map_path: Path


@dataclass
class _WorkspaceParams:
    map_content: str
    task_content: str = TASK_FRONTMATTER


def _build_workspace(tmp_path: Path, params: _WorkspaceParams) -> _WorkspaceFixture:
    """Write MAP.md and task file to tmp_path."""
    map_path = tmp_path / "MAP.md"
    map_path.write_text(params.map_content, encoding="utf-8")
    task_path = tmp_path / "task_001_foo.md"
    task_path.write_text(params.task_content, encoding="utf-8")
    return _WorkspaceFixture(workspace=tmp_path, map_path=map_path)


def _make_config(workspace: Path, is_dry_run: bool = False) -> OrchestrateConfig:
    """Build OrchestrateConfig for tests."""
    return OrchestrateConfig(workspace=workspace, is_dry_run=is_dry_run)


# ---- Unit tests for pure handlers ----

def _make_all_done_ctx(tmp_path: Path) -> CycleContext:
    """Build a minimal CycleContext pointing at tmp_path."""
    config = OrchestrateConfig(workspace=tmp_path, is_dry_run=False)
    return CycleContext(config=config, map_path=tmp_path / "MAP.md", task_lookup={})


class TestHandleAllDone:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_returns_exit_all_done(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """_handle_all_done returns exit code 0 when audit passes."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.exit_code == EXIT_ALL_DONE

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_returns_empty_output(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """_handle_all_done returns empty output dict when audit passes."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.output == {}


class TestHandleWaiting:
    def test_returns_exit_waiting(self) -> None:
        """_handle_waiting returns exit code 2."""
        result = _handle_waiting()
        assert result.exit_code == EXIT_WAITING


class TestHandleEscalate:
    def test_returns_exit_blocked(self) -> None:
        """_handle_escalate returns exit code 3."""
        action = Action(kind=ESCALATE_BLOCKED, tasks=["task_001"], detail="blocked")
        result = _handle_escalate(action)
        assert result.exit_code == EXIT_BLOCKED

    def test_output_has_escalate_action(self) -> None:
        """_handle_escalate output action is 'escalate'."""
        action = Action(kind=ESCALATE_BLOCKED, tasks=["task_001"], detail="blocked")
        result = _handle_escalate(action)
        assert result.output["action"] == "escalate"

    def test_output_contains_task_ids(self) -> None:
        """_handle_escalate output includes blocked task ids."""
        action = Action(kind=ESCALATE_BLOCKED, tasks=["task_001", "task_002"], detail="blocked")
        result = _handle_escalate(action)
        assert "task_001" in result.output["tasks"]
        assert "task_002" in result.output["tasks"]


# ---- Integration tests using _run_cycle ----

class TestRunCycleMissingMap:
    def test_missing_map_returns_exit_error(self, tmp_path: Path) -> None:
        """Missing MAP.md returns EXIT_ERROR."""
        config = _make_config(tmp_path)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ERROR

    def test_missing_map_output_detail(self, tmp_path: Path) -> None:
        """Missing MAP.md output contains 'MAP.md not found'."""
        config = _make_config(tmp_path)
        result = _run_cycle(config)
        assert "MAP.md not found" in result.output["detail"]


class TestRunCycleAllDone:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_all_done_returns_exit_zero(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """All DONE tasks returns EXIT_ALL_DONE."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_ALL_DONE))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ALL_DONE


class TestRunCycleWaiting:
    def test_in_progress_returns_exit_waiting(self, tmp_path: Path) -> None:
        """Only IN_PROGRESS tasks returns EXIT_WAITING."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_IN_PROGRESS))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_WAITING


class TestRunCycleBlocked:
    def test_blocked_returns_exit_blocked(self, tmp_path: Path) -> None:
        """BLOCKED tasks return EXIT_BLOCKED."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_BLOCKED))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_BLOCKED

    def test_blocked_output_action_is_escalate(self, tmp_path: Path) -> None:
        """BLOCKED tasks produce action='escalate' in output."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_BLOCKED))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.output["action"] == "escalate"


class TestRunCycleDryRun:
    @patch("scripts.orchestrate.dispatch_worker")
    def test_dry_run_does_not_call_dispatch(self, mock_dispatch: MagicMock, tmp_path: Path) -> None:
        """Dry-run mode skips subprocess calls."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace, is_dry_run=True)
        _run_cycle(config)
        mock_dispatch.assert_not_called()

    @patch("scripts.orchestrate.update_map_status")
    def test_dry_run_does_not_flip_status(self, mock_flip: MagicMock, tmp_path: Path) -> None:
        """Dry-run mode skips status flips."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace, is_dry_run=True)
        _run_cycle(config)
        mock_flip.assert_not_called()

    @patch("scripts.orchestrate.dispatch_worker")
    def test_dry_run_returns_action_taken(self, mock_dispatch: MagicMock, tmp_path: Path) -> None:
        """Dry-run still returns EXIT_ACTION_TAKEN for pending tasks."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace, is_dry_run=True)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ACTION_TAKEN


class TestRunCycleDispatchWave:
    @patch("scripts.orchestrate.dispatch_worker")
    @patch("scripts.orchestrate.update_map_status")
    def test_pending_task_dispatched(self, mock_flip: MagicMock, mock_dispatch: MagicMock, tmp_path: Path) -> None:
        """PENDING task with no deps gets dispatched."""
        mock_dispatch.return_value = MagicMock(exit_code=0)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ACTION_TAKEN

    @patch("scripts.orchestrate.dispatch_worker")
    @patch("scripts.orchestrate.update_map_status")
    def test_dispatch_wave_output_action(self, mock_flip: MagicMock, mock_dispatch: MagicMock, tmp_path: Path) -> None:
        """dispatch_wave produces action='dispatch_wave' in output."""
        mock_dispatch.return_value = MagicMock(exit_code=0)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.output["action"] == "dispatch_wave"

    @patch("scripts.orchestrate.dispatch_worker")
    @patch("scripts.orchestrate.update_map_status")
    def test_worker_failure_flips_to_failed(self, mock_flip: MagicMock, mock_dispatch: MagicMock, tmp_path: Path) -> None:
        """Worker non-zero exit flips status to FAILED."""
        mock_dispatch.return_value = MagicMock(exit_code=1)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
        config = _make_config(fx.workspace)
        _run_cycle(config)
        flip_calls = [call[0][0].new_status for call in mock_flip.call_args_list]
        assert "FAILED" in flip_calls


class TestRunCycleAdvisorApprove:
    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_advisor_approve_flips_to_done(self, mock_flip: MagicMock, mock_advisor: MagicMock, tmp_path: Path) -> None:
        """APPROVE verdict flips REVIEW->DONE."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="APPROVE\nAll good")
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW))
        config = _make_config(fx.workspace)
        _run_cycle(config)
        flip_calls = [call[0][0].new_status for call in mock_flip.call_args_list]
        assert "DONE" in flip_calls

    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_advisor_approve_returns_action_taken(self, mock_flip: MagicMock, mock_advisor: MagicMock, tmp_path: Path) -> None:
        """APPROVE verdict returns EXIT_ACTION_TAKEN."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="APPROVE")
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ACTION_TAKEN


class TestRunCycleAdvisorRevise:
    @patch("scripts.orchestrate.dispatch_revise")
    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_advisor_revise_re_dispatches_worker(
        self, mock_flip: MagicMock, mock_advisor: MagicMock, mock_revise: MagicMock, tmp_path: Path
    ) -> None:
        """REVISE verdict triggers re-dispatch with guidance."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="REVISE\nFix the thing")
        mock_revise.return_value = MagicMock(exit_code=0)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        mock_revise.assert_called_once()
        assert result.exit_code == EXIT_ACTION_TAKEN

    @patch("scripts.orchestrate.dispatch_revise")
    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_revise_output_action_is_revise_worker(
        self, mock_flip: MagicMock, mock_advisor: MagicMock, mock_revise: MagicMock, tmp_path: Path
    ) -> None:
        """REVISE verdict output action is 'revise_worker'."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="REVISE\nFix it")
        mock_revise.return_value = MagicMock(exit_code=0)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert result.output["action"] == "revise_worker"


class TestRunCycleReviseFailure:
    @patch("scripts.orchestrate.dispatch_revise")
    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_revise_dispatch_failure_flips_to_failed(
        self, mock_flip: MagicMock, mock_advisor: MagicMock, mock_revise: MagicMock, tmp_path: Path
    ) -> None:
        """REVISE dispatch failure flips task to FAILED and returns EXIT_ERROR."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="REVISE\nFix the thing")
        mock_revise.return_value = MagicMock(exit_code=1)
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        flip_calls = [call[0][0].new_status for call in mock_flip.call_args_list]
        assert "FAILED" in flip_calls
        assert result.exit_code == EXIT_ERROR


class TestRunCycleAdvisorBlocked:
    @patch("scripts.orchestrate.dispatch_advisor")
    @patch("scripts.orchestrate.update_map_status")
    def test_max_revise_rounds_flips_to_blocked(self, mock_flip: MagicMock, mock_advisor: MagicMock, tmp_path: Path) -> None:
        """After 3 REVISE rounds, task is flipped to BLOCKED."""
        mock_advisor.return_value = MagicMock(exit_code=0, stdout="REVISE\nStill broken")
        task_with_revises = TASK_FRONTMATTER.replace(
            "## Registers\n— empty —",
            "## Registers\nREVISE round 1 (nonce 000000): issue\nREVISE round 2 (nonce 000000): issue\nREVISE round 3 (nonce 000000): issue",
        )
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_REVIEW, task_with_revises))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        flip_calls = [call[0][0].new_status for call in mock_flip.call_args_list]
        assert "BLOCKED" in flip_calls
        assert result.exit_code == EXIT_BLOCKED


class TestJsonOutput:
    def test_dispatch_wave_output_has_required_keys(self, tmp_path: Path) -> None:
        """dispatch_wave JSON output contains action, tasks, detail keys."""
        with patch("scripts.orchestrate.dispatch_worker") as mock_dispatch, \
             patch("scripts.orchestrate.update_map_status"):
            mock_dispatch.return_value = MagicMock(exit_code=0)
            fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_PENDING))
            config = _make_config(fx.workspace)
            result = _run_cycle(config)
            assert "action" in result.output
            assert "tasks" in result.output
            assert "detail" in result.output

    def test_escalate_output_has_required_keys(self, tmp_path: Path) -> None:
        """escalate JSON output contains action, tasks, detail keys."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_BLOCKED))
        config = _make_config(fx.workspace)
        result = _run_cycle(config)
        assert "action" in result.output
        assert "tasks" in result.output
        assert "detail" in result.output


class TestAuditGateClean:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_clean_audit_returns_exit_all_done(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Clean audit writes sentinel, calls session_close, returns EXIT_ALL_DONE."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.exit_code == EXIT_ALL_DONE

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_clean_audit_writes_sentinel(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Clean audit creates .audit_clean sentinel file."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        _handle_all_done(_make_all_done_ctx(tmp_path))
        assert (tmp_path / ".audit_clean").exists()

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_clean_audit_calls_session_close(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Clean audit triggers session_close exactly once."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        _handle_all_done(_make_all_done_ctx(tmp_path))
        mock_close.assert_called_once()


class TestAuditGateFailed:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_failed_audit_returns_exit_audit_failed(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Failed audit returns EXIT_AUDIT_FAILED without calling session_close."""
        mock_audit.return_value = AuditGateResult(is_clean=False, detail="audit_discipline failed: F1 violation")
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.exit_code == EXIT_AUDIT_FAILED

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_failed_audit_output_has_detail(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Failed audit output carries audit_failed action and detail."""
        detail = "audit_discipline failed: F1 violation"
        mock_audit.return_value = AuditGateResult(is_clean=False, detail=detail)
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.output["action"] == "audit_failed"
        assert detail in result.output["detail"]

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_failed_audit_does_not_call_session_close(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Failed audit never calls session_close."""
        mock_audit.return_value = AuditGateResult(is_clean=False, detail="check_deps failed: broken import")
        _handle_all_done(_make_all_done_ctx(tmp_path))
        mock_close.assert_not_called()


class TestAuditGateSentinel:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_sentinel_skips_audit(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Pre-existing sentinel skips audit scripts entirely."""
        (tmp_path / ".audit_clean").touch()
        _handle_all_done(_make_all_done_ctx(tmp_path))
        mock_audit.assert_not_called()

    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_sentinel_still_calls_session_close(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Pre-existing sentinel still triggers session_close."""
        mock_close.return_value = True
        (tmp_path / ".audit_clean").touch()
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        mock_close.assert_called_once()
        assert result.exit_code == EXIT_ALL_DONE


class TestAuditGateDryRun:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_dry_run_all_done_skips_audit(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """dry-run mode: all DONE pipeline does not invoke audit scripts or session_close."""
        fx = _build_workspace(tmp_path, _WorkspaceParams(MAP_ALL_DONE))
        config = _make_config(fx.workspace, is_dry_run=True)
        result = _run_cycle(config)
        assert result.exit_code == EXIT_ALL_DONE
        mock_audit.assert_not_called()
        mock_close.assert_not_called()
        assert not (tmp_path / ".audit_clean").exists()


class TestAuditGateSessionCloseFailure:
    @patch("scripts.orchestrate._run_audit_scripts")
    @patch("scripts.orchestrate._run_session_close")
    def test_failing_session_close_yields_exit_error(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        """Failing session_close returns EXIT_ERROR even when audit passes."""
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = False
        result = _handle_all_done(_make_all_done_ctx(tmp_path))
        assert result.exit_code == EXIT_ERROR
        assert result.output["detail"] == "session_close failed"
