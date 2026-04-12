from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.fsm_core.dispatch_contract import (
    AdvisorDispatchRequest,
    DispatchResult,
    ReviseDispatchRequest,
    WorkerDispatchRequest,
)
from src.fsm_core.dispatch_router import dispatch_advisor, dispatch_revise, dispatch_workers_parallel


class TestDispatchWorkersParallelRouting:
    @patch("src.fsm_core.dispatch_router.claude_session_backend.dispatch_workers_parallel")
    def test_claude_session_routes_to_backend(self, mock_backend: MagicMock) -> None:
        mock_backend.return_value = [DispatchResult(exit_code=125, stdout="queued", stderr="")]
        req = WorkerDispatchRequest(task_path="/tmp/task.md", dispatch_role="fsm-executor")
        workspace = Path("/tmp")
        result = dispatch_workers_parallel([req], dispatch_mode="claude_session", workspace=workspace)
        assert len(result) == 1
        mock_backend.assert_called_once()
        assert mock_backend.call_args.kwargs["workspace"] == workspace

    def test_non_claude_mode_is_rejected(self) -> None:
        req = WorkerDispatchRequest(task_path="/tmp/task.md", dispatch_role="fsm-executor")
        with pytest.raises(ValueError):
            dispatch_workers_parallel([req], dispatch_mode="subprocess")


class TestDispatchAdvisorRouting:
    @patch("src.fsm_core.dispatch_router.claude_session_backend.dispatch_advisor")
    def test_claude_session_routes_to_backend(self, mock_backend: MagicMock) -> None:
        mock_backend.return_value = DispatchResult(exit_code=125, stdout="queued", stderr="")
        req = AdvisorDispatchRequest(task_paths=["/tmp/task.md"])
        dispatch_advisor(req, dispatch_mode="claude_session", workspace=Path("/tmp"))
        mock_backend.assert_called_once()


class TestDispatchReviseRouting:
    @patch("src.fsm_core.dispatch_router.claude_session_backend.dispatch_revise")
    def test_claude_session_routes_to_backend(self, mock_backend: MagicMock) -> None:
        mock_backend.return_value = DispatchResult(exit_code=125, stdout="queued", stderr="")
        req = ReviseDispatchRequest(
            task_path="/tmp/task.md",
            guidance="Fix",
            dispatch_role="fsm-executor",
        )
        result = dispatch_revise(req, dispatch_mode="claude_session", workspace=Path("/tmp"))
        assert result.exit_code == 125
        mock_backend.assert_called_once()
