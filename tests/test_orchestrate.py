"""Tests for orchestrate.py in claude-session-native dispatch mode."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.orchestrate import (
    CHECKPOINT_SENTINEL,
    EXIT_ACTION_TAKEN,
    EXIT_ALL_DONE,
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_WAITING,
    AuditGateResult,
    OrchestrateConfig,
    _run_cycle,
    _run_startup_checks,
)
from src.fsm_core.claude_session_backend import (
    AdvisorIntentRequest,
    AdvisorScannerConfig,
    ResultPayload,
    enqueue_advisor_intent,
    enqueue_worker_intents,
    write_result_for_intent,
)
from src.fsm_core.dispatch_contract import WorkerDispatchRequest


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

MAP_EXECUTING: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ EXECUTING
"""

MAP_IN_PROGRESS: str = """\
# MAP

## Active Tasks

  [task_001_foo.md] ........ IN_PROGRESS
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


def _task_content(state: str) -> str:
    return f"""\
---
id: task_001
name: foo
state: {state}
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
class WorkspaceFixture:
    workspace: Path
    map_path: Path
    task_path: Path


def _build_workspace(tmp_path: Path, map_content: str, task_state: str) -> WorkspaceFixture:
    map_path = tmp_path / "MAP.md"
    map_path.write_text(map_content, encoding="utf-8")
    task_path = tmp_path / "task_001_foo.md"
    task_path.write_text(_task_content(task_state), encoding="utf-8")
    return WorkspaceFixture(workspace=tmp_path, map_path=map_path, task_path=task_path)


def _make_config(workspace: Path, *, is_dry_run: bool = False) -> OrchestrateConfig:
    return OrchestrateConfig(workspace=workspace, is_dry_run=is_dry_run, dispatch_mode="claude_session")


def _enqueue_advisor(workspace: Path, task_path: Path, scanner_config: AdvisorScannerConfig | None = None):
    """Test helper: enqueue an advisor intent with minimal boilerplate."""
    from src.fsm_core.dispatch_contract import AdvisorDispatchRequest as ADR
    req = ADR(task_paths=[str(task_path)])
    cfg = scanner_config or AdvisorScannerConfig()
    return enqueue_advisor_intent(workspace, AdvisorIntentRequest(request=req, scanner_config=cfg))


class TestBasicCycle:
    def test_missing_map_returns_exit_error(self, tmp_path: Path) -> None:
        result = _run_cycle(_make_config(tmp_path))
        assert result.exit_code == EXIT_ERROR
        assert "MAP.md not found" in result.output["detail"]

    def test_blocked_returns_exit_blocked(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_BLOCKED, "BLOCKED")
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_BLOCKED
        assert result.output["action"] == "escalate"

    def test_in_progress_without_results_returns_waiting(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_IN_PROGRESS, "IN_PROGRESS")
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_WAITING

    @patch("scripts.orchestrate._run_audit_if_needed")
    @patch("scripts.orchestrate._run_session_close")
    def test_all_done_runs_close_and_returns_zero(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_ALL_DONE, "DONE")
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ALL_DONE


class TestDispatchQueueing:
    @patch("scripts.orchestrate.enqueue_worker_intents")
    @patch("scripts.orchestrate.update_map_status")
    def test_pending_task_queues_worker_intent(
        self, mock_flip: MagicMock, mock_enqueue: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_PENDING, "PENDING")
        mock_enqueue.return_value = [MagicMock(intent_id="intent_1")]
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ACTION_TAKEN
        assert result.output["action"] == "dispatch_wave"
        mock_enqueue.assert_called_once()
        statuses = [c[0][0].new_status for c in mock_flip.call_args_list]
        assert "IN_PROGRESS" in statuses

    @patch("scripts.orchestrate.enqueue_advisor_intent")
    @patch("scripts.orchestrate.update_map_status")
    def test_review_task_queues_advisor_intent(
        self, mock_flip: MagicMock, mock_enqueue: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_REVIEW, "REVIEW")
        mock_enqueue.return_value = MagicMock(intent_id="intent_adv")
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ACTION_TAKEN
        assert result.output["action"] == "dispatch_advisor"
        assert mock_enqueue.call_count == 2
        statuses = [c[0][0].new_status for c in mock_flip.call_args_list]
        assert "EXECUTING" in statuses

    @patch("scripts.orchestrate.enqueue_worker_intents")
    def test_checkpoint_sentinel_skips_dispatch(self, mock_enqueue: MagicMock, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_PENDING, "PENDING")
        (fx.workspace / CHECKPOINT_SENTINEL).write_text("{}", encoding="utf-8")
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_WAITING
        mock_enqueue.assert_not_called()


class TestResultApplication:
    @patch("scripts.orchestrate.enqueue_advisor_intent")
    def test_worker_result_is_applied_before_decision(self, mock_adv_enqueue: MagicMock, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_IN_PROGRESS, "IN_PROGRESS")
        worker_req = WorkerDispatchRequest(task_path=str(fx.task_path), dispatch_role="fsm-executor")
        worker_intent = enqueue_worker_intents(fx.workspace, [worker_req])[0]
        payload = ResultPayload(intent_id=worker_intent.intent_id, exit_code=0, stdout="ok", stderr="")
        write_result_for_intent(fx.workspace, payload)
        mock_adv_enqueue.return_value = MagicMock(intent_id="intent_adv")
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ACTION_TAKEN
        # worker result flips IN_PROGRESS->REVIEW, then cycle queues advisor and flips to EXECUTING
        updated = fx.map_path.read_text(encoding="utf-8")
        assert "EXECUTING" in updated
        applied_dir = fx.workspace / ".fsm-results" / "applied"
        assert len(list(applied_dir.glob("*.json"))) == 1

    @patch("scripts.orchestrate._run_audit_if_needed")
    @patch("scripts.orchestrate._run_session_close")
    def test_advisor_approve_result_marks_done(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        advisor_intent = _enqueue_advisor(fx.workspace, fx.task_path)
        payload = ResultPayload(intent_id=advisor_intent.intent_id, exit_code=0, stdout="APPROVE\nok", stderr="")
        write_result_for_intent(fx.workspace, payload)
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ALL_DONE
        assert "DONE" in fx.map_path.read_text(encoding="utf-8")

    @patch("scripts.orchestrate._run_audit_if_needed")
    @patch("scripts.orchestrate._run_session_close")
    def test_bug_scanner_pair_approve_marks_done(
        self, mock_close: MagicMock, mock_audit: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        left = _enqueue_advisor(fx.workspace, fx.task_path, AdvisorScannerConfig(
            pair_key="pair:task_001", scanner_index=0, scanner_total=2,
        ))
        right = _enqueue_advisor(fx.workspace, fx.task_path, AdvisorScannerConfig(
            pair_key="pair:task_001", scanner_index=1, scanner_total=2,
        ))
        left_payload = ResultPayload(intent_id=left.intent_id, exit_code=0, stdout="APPROVE\nleft", stderr="")
        write_result_for_intent(fx.workspace, left_payload)
        right_payload = ResultPayload(intent_id=right.intent_id, exit_code=0, stdout="APPROVE\nright", stderr="")
        write_result_for_intent(fx.workspace, right_payload)
        mock_audit.return_value = AuditGateResult(is_clean=True, detail="audit clean")
        mock_close.return_value = True
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ALL_DONE
        assert "DONE" in fx.map_path.read_text(encoding="utf-8")

    def test_bug_scanner_pair_waits_for_both_results(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        left = _enqueue_advisor(fx.workspace, fx.task_path, AdvisorScannerConfig(
            pair_key="pair:task_001", scanner_index=0, scanner_total=2,
        ))
        left_payload = ResultPayload(intent_id=left.intent_id, exit_code=0, stdout="APPROVE\nleft", stderr="")
        write_result_for_intent(fx.workspace, left_payload)
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_WAITING
        assert "EXECUTING" in fx.map_path.read_text(encoding="utf-8")
        pending = list((fx.workspace / ".fsm-results").glob("*.json"))
        assert len(pending) == 1

    @patch("scripts.orchestrate.enqueue_worker_intents")
    def test_advisor_revise_result_appends_register_and_redispatches(
        self, mock_worker_enqueue: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        advisor_intent = _enqueue_advisor(fx.workspace, fx.task_path)
        revise_text = "REVISE\nFAILING TASKS: task_001\nfix it"
        payload = ResultPayload(intent_id=advisor_intent.intent_id, exit_code=0, stdout=revise_text, stderr="")
        write_result_for_intent(fx.workspace, payload)
        mock_worker_enqueue.return_value = [MagicMock(intent_id="intent_worker")]
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ACTION_TAKEN
        assert "IN_PROGRESS" in fx.map_path.read_text(encoding="utf-8")
        assert "REVISE round 1" in fx.task_path.read_text(encoding="utf-8")
        reqs = mock_worker_enqueue.call_args.args[1]
        assert reqs[0].dispatch_role == "debugger"

    @patch("scripts.orchestrate.enqueue_worker_intents")
    def test_advisor_revise_routes_simple_fixes_to_code_fixer(
        self, mock_worker_enqueue: MagicMock, tmp_path: Path
    ) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        advisor_intent = _enqueue_advisor(fx.workspace, fx.task_path)
        revise_text = "REVISE\nFAILING TASKS: task_001\nlint and import cleanup required"
        payload = ResultPayload(intent_id=advisor_intent.intent_id, exit_code=0, stdout=revise_text, stderr="")
        write_result_for_intent(fx.workspace, payload)
        mock_worker_enqueue.return_value = [MagicMock(intent_id="intent_worker")]
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_ACTION_TAKEN
        reqs = mock_worker_enqueue.call_args.args[1]
        assert reqs[0].dispatch_role == "code-fixer"

    def test_advisor_revise_over_limit_blocks_task(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_EXECUTING, "EXECUTING")
        content = fx.task_path.read_text(encoding="utf-8")
        content = content.replace(
            "## Registers\n— empty —",
            "## Registers\nREVISE round 1 (nonce 000000): x\nREVISE round 2 (nonce 000000): y\nREVISE round 3 (nonce 000000): z",
        )
        fx.task_path.write_text(content, encoding="utf-8")
        advisor_intent = _enqueue_advisor(fx.workspace, fx.task_path)
        payload = ResultPayload(intent_id=advisor_intent.intent_id, exit_code=0, stdout="REVISE\nFAILING TASKS: task_001\nstill bad", stderr="")
        write_result_for_intent(fx.workspace, payload)
        result = _run_cycle(_make_config(fx.workspace))
        assert result.exit_code == EXIT_BLOCKED
        assert "BLOCKED" in fx.map_path.read_text(encoding="utf-8")


class TestStartupChecks:
    def test_strict_state_drift_raises(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_BLOCKED, "PENDING")
        config = OrchestrateConfig(
            workspace=fx.workspace,
            is_dry_run=False,
            dispatch_mode="claude_session",
            should_strict_map_check=True,
        )
        with pytest.raises(RuntimeError):
            _run_startup_checks(config)

    def test_sync_task_state_to_map_rewrites_frontmatter(self, tmp_path: Path) -> None:
        fx = _build_workspace(tmp_path, MAP_BLOCKED, "PENDING")
        config = OrchestrateConfig(
            workspace=fx.workspace,
            is_dry_run=False,
            dispatch_mode="claude_session",
            should_sync_task_state=True,
        )
        _run_startup_checks(config)
        content = fx.task_path.read_text(encoding="utf-8")
        assert "state: BLOCKED" in content
