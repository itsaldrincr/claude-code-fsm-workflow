import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.fsm_core.subprocess_dispatch import (
    ADVISOR_MODEL,
    CLAUDE_CMD,
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_MAP,
    AdvisorDispatchRequest,
    DispatchResult,
    ReviseDispatchRequest,
    WorkerDispatchRequest,
    dispatch_advisor,
    dispatch_revise,
    dispatch_worker,
)


class TestModelMapping:
    """Test MODEL_MAP constants."""

    def test_executor_maps_to_haiku(self) -> None:
        """fsm-executor should map to haiku."""
        assert MODEL_MAP["fsm-executor"] == "haiku"

    def test_integrator_maps_to_sonnet(self) -> None:
        """fsm-integrator should map to sonnet."""
        assert MODEL_MAP["fsm-integrator"] == "sonnet"

    def test_advisor_model_is_opus(self) -> None:
        """ADVISOR_MODEL should be opus."""
        assert ADVISOR_MODEL == "opus"


class TestDispatchWorker:
    """Test dispatch_worker function."""

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_dispatch_executor_uses_haiku(self, mock_run: MagicMock) -> None:
        """Worker dispatch with fsm-executor should use haiku model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        dispatch_worker(req)
        call_args = mock_run.call_args
        assert "--model" in call_args[0][0]
        idx = call_args[0][0].index("--model")
        assert call_args[0][0][idx + 1] == "haiku"

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_dispatch_integrator_uses_sonnet(self, mock_run: MagicMock) -> None:
        """Worker dispatch with fsm-integrator should use sonnet model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = WorkerDispatchRequest(
            task_path="/path/to/task_456.md",
            dispatch_role="fsm-integrator",
        )
        dispatch_worker(req)
        call_args = mock_run.call_args
        assert "--model" in call_args[0][0]
        idx = call_args[0][0].index("--model")
        assert call_args[0][0][idx + 1] == "sonnet"

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_worker_prompt_format(self, mock_run: MagicMock) -> None:
        """Worker prompt should match SOP template exactly."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        task_path = "/path/to/task_123.md"
        req = WorkerDispatchRequest(
            task_path=task_path,
            dispatch_role="fsm-executor",
        )
        dispatch_worker(req)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        prompt = cmd[2]  # cmd is [claude, -p, prompt, --model, model]
        assert f"Execute task file: {task_path}" in prompt
        assert "This task file is self-contained." in prompt
        assert "Read it, follow its Protocol" in prompt


class TestDispatchAdvisor:
    """Test dispatch_advisor function."""

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_advisor_uses_opus(self, mock_run: MagicMock) -> None:
        """Advisor dispatch should always use opus model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = AdvisorDispatchRequest(task_path="/path/to/task_123.md")
        dispatch_advisor(req)
        call_args = mock_run.call_args
        assert "--model" in call_args[0][0]
        idx = call_args[0][0].index("--model")
        assert call_args[0][0][idx + 1] == "opus"

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_advisor_prompt_format(self, mock_run: MagicMock) -> None:
        """Advisor prompt should match spec template."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        task_path = "/path/to/task_456.md"
        req = AdvisorDispatchRequest(task_path=task_path)
        dispatch_advisor(req)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        prompt = cmd[2]
        assert f"Review task file: {task_path}" in prompt
        assert "Read the task file and every file listed in its ## Files section" in prompt
        assert "Evaluate against the task's Acceptance Criteria" in prompt
        assert "APPROVE - if all acceptance criteria are met" in prompt
        assert "REVISE - if issues were found" in prompt


class TestDispatchRevise:
    """Test dispatch_revise function."""

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_revise_executor_uses_haiku(self, mock_run: MagicMock) -> None:
        """REVISE dispatch with fsm-executor should use haiku model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = ReviseDispatchRequest(
            task_path="/path/to/task_123.md",
            guidance="Fix the implementation.",
            dispatch_role="fsm-executor",
        )
        dispatch_revise(req)
        call_args = mock_run.call_args
        assert "--model" in call_args[0][0]
        idx = call_args[0][0].index("--model")
        assert call_args[0][0][idx + 1] == "haiku"

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_revise_integrator_uses_sonnet(self, mock_run: MagicMock) -> None:
        """REVISE dispatch with fsm-integrator should use sonnet model."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = ReviseDispatchRequest(
            task_path="/path/to/task_123.md",
            guidance="Fix the implementation.",
            dispatch_role="fsm-integrator",
        )
        dispatch_revise(req)
        call_args = mock_run.call_args
        assert "--model" in call_args[0][0]
        idx = call_args[0][0].index("--model")
        assert call_args[0][0][idx + 1] == "sonnet"

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_revise_prompt_includes_prefix(self, mock_run: MagicMock) -> None:
        """REVISE prompt should start with REVISE: prefix."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        guidance = "Address the bugs in the implementation."
        req = ReviseDispatchRequest(
            task_path="/path/to/task_123.md",
            guidance=guidance,
            dispatch_role="fsm-executor",
        )
        dispatch_revise(req)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        prompt = cmd[2]
        assert "REVISE: The advisor found issues" in prompt
        assert guidance in prompt
        assert "Execute task file:" in prompt


class TestDispatchResult:
    """Test DispatchResult dataclass."""

    def test_dispatch_result_construction(self) -> None:
        """DispatchResult should construct with exit_code, stdout, stderr."""
        result = DispatchResult(
            exit_code=0,
            stdout="output",
            stderr="",
        )
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""


class TestErrorHandling:
    """Test error handling in subprocess calls."""

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_timeout_expired_handled(self, mock_run: MagicMock) -> None:
        """TimeoutExpired should be caught and return error result."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", DEFAULT_TIMEOUT_SECONDS)
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        result = dispatch_worker(req)
        assert result.exit_code == 124
        assert "Timeout" in result.stderr

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_file_not_found_handled(self, mock_run: MagicMock) -> None:
        """FileNotFoundError should return error result."""
        mock_run.side_effect = FileNotFoundError()
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        result = dispatch_worker(req)
        assert result.exit_code == 127
        assert "not found" in result.stderr

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_subprocess_error_captured(self, mock_run: MagicMock) -> None:
        """Subprocess non-zero exit should be captured in result."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="some output",
            stderr="some error",
        )
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        result = dispatch_worker(req)
        assert result.exit_code == 1
        assert result.stdout == "some output"
        assert result.stderr == "some error"


class TestCommandConstruction:
    """Test that commands are properly constructed."""

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_claude_command_structure(self, mock_run: MagicMock) -> None:
        """Command should be [claude, -p, <prompt>, --model, <model>]."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        dispatch_worker(req)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == CLAUDE_CMD
        assert cmd[1] == "-p"
        assert isinstance(cmd[2], str)  # prompt
        assert cmd[3] == "--model"
        assert isinstance(cmd[4], str)  # model

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_timeout_passed_to_subprocess(self, mock_run: MagicMock) -> None:
        """DEFAULT_TIMEOUT_SECONDS should be passed to subprocess.run."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        dispatch_worker(req)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("timeout") == DEFAULT_TIMEOUT_SECONDS

    @patch("src.fsm_core.subprocess_dispatch.subprocess.run")
    def test_capture_output_enabled(self, mock_run: MagicMock) -> None:
        """subprocess.run should capture_output=True and text=True."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        req = WorkerDispatchRequest(
            task_path="/path/to/task_123.md",
            dispatch_role="fsm-executor",
        )
        dispatch_worker(req)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("capture_output") is True
        assert call_kwargs.get("text") is True
