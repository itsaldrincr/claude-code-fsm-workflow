import subprocess
from dataclasses import dataclass

# Model mapping: dispatch role -> model name
MODEL_MAP = {
    "fsm-executor": "haiku",
    "fsm-integrator": "sonnet",
}

ADVISOR_MODEL = "opus"
DEFAULT_TIMEOUT_SECONDS = 900
CLAUDE_CMD = "claude"
TIMEOUT_EXIT_CODE = 124
NOT_FOUND_EXIT_CODE = 127


@dataclass
class WorkerDispatchRequest:
    """Request to dispatch a worker task."""

    task_path: str
    dispatch_role: str


@dataclass
class AdvisorDispatchRequest:
    """Request to dispatch an advisor review."""

    task_path: str


@dataclass
class ReviseDispatchRequest:
    """Request to dispatch a REVISE round."""

    task_path: str
    guidance: str
    dispatch_role: str


@dataclass
class DispatchResult:
    """Result from subprocess dispatch."""

    exit_code: int
    stdout: str
    stderr: str


def _build_worker_prompt(task_path: str) -> str:
    """Return the standard worker dispatch prompt template."""
    return f"""Execute task file: {task_path}

This task file is self-contained. Read it, follow its Protocol, write code per its Program steps, update Registers with nonce proof, set state to DONE on success."""


def _build_advisor_prompt(task_path: str) -> str:
    """Return the advisor dispatch prompt template."""
    return f"""Review task file: {task_path}

Read the task file and every file listed in its ## Files section (both Creates and Modifies paths).
Evaluate against the task's Acceptance Criteria and the project's coding discipline (CLAUDE.md).

Return your verdict as the FIRST LINE of your response:
APPROVE - if all acceptance criteria are met and coding discipline is followed.
REVISE - if issues were found.

If REVISE, list each issue and corrective guidance below the verdict line."""


def _build_revise_prompt(request: ReviseDispatchRequest) -> str:
    """Return REVISE-prefixed worker prompt with guidance."""
    base_prompt = _build_worker_prompt(request.task_path)
    return f"""REVISE: The advisor found issues with your previous output. Address each issue below, then re-execute the task.

Issues:
{request.guidance}

{base_prompt}"""


def _timeout_result(error: subprocess.TimeoutExpired) -> DispatchResult:
    """Build DispatchResult for timeout error."""
    return DispatchResult(
        exit_code=TIMEOUT_EXIT_CODE,
        stdout="",
        stderr=f"Timeout after {DEFAULT_TIMEOUT_SECONDS}s: {error}",
    )


def _not_found_result() -> DispatchResult:
    """Build DispatchResult for command not found error."""
    return DispatchResult(
        exit_code=NOT_FOUND_EXIT_CODE,
        stdout="",
        stderr=f"Command not found: {CLAUDE_CMD}",
    )


def _called_process_result(error: subprocess.CalledProcessError) -> DispatchResult:
    """Build DispatchResult for CalledProcessError."""
    return DispatchResult(
        exit_code=error.returncode,
        stdout=error.stdout or "",
        stderr=error.stderr or "",
    )


def _success_result(result: subprocess.CompletedProcess) -> DispatchResult:
    """Build DispatchResult from successful subprocess completion."""
    return DispatchResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _run_claude(prompt: str, model: str) -> DispatchResult:
    """Execute claude CLI with given prompt and model."""
    cmd = [CLAUDE_CMD, "-p", prompt, "--model", model]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        return _success_result(result)
    except subprocess.TimeoutExpired as e:
        return _timeout_result(e)
    except subprocess.CalledProcessError as e:
        return _called_process_result(e)
    except FileNotFoundError:
        return _not_found_result()


def dispatch_worker(request: WorkerDispatchRequest) -> DispatchResult:
    """Dispatch a worker task with appropriate model tier."""
    model = MODEL_MAP.get(request.dispatch_role, "haiku")
    prompt = _build_worker_prompt(request.task_path)
    return _run_claude(prompt, model)


def dispatch_advisor(request: AdvisorDispatchRequest) -> DispatchResult:
    """Dispatch an advisor review (always Opus)."""
    prompt = _build_advisor_prompt(request.task_path)
    return _run_claude(prompt, ADVISOR_MODEL)


def dispatch_revise(request: ReviseDispatchRequest) -> DispatchResult:
    """Dispatch a REVISE round using the task's original dispatch role."""
    prompt = _build_revise_prompt(request)
    return _run_claude(prompt, MODEL_MAP.get(request.dispatch_role, "haiku"))
