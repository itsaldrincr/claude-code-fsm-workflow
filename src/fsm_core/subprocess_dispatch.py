import concurrent.futures
import subprocess
from dataclasses import dataclass

# Model mapping: dispatch role -> model name
MODEL_MAP = {
    "fsm-executor": "haiku",
    "fsm-integrator": "sonnet",
}

ADVISOR_MODEL = "opus"
DEFAULT_TIMEOUT_SECONDS = 1800
CLAUDE_CMD = "claude"
TIMEOUT_EXIT_CODE = 124
NOT_FOUND_EXIT_CODE = 127
MAX_PARALLEL_WORKERS: int = 8


@dataclass
class WorkerDispatchRequest:
    """Request to dispatch a worker task."""

    task_path: str
    dispatch_role: str


@dataclass
class AdvisorDispatchRequest:
    """Request to dispatch an advisor review across a wave batch."""

    task_paths: list[str]


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

This task file is self-contained. Read it in full, then follow its Program steps exactly.

HARD REQUIREMENTS — violations count as task failure:

1. REAL TOOL CALLS ONLY. Every file in the task's `## Files` Creates: and Modifies: sections must be produced via actual Write or Edit tool invocations. Do NOT generate code as response text without calling the tool — the advisor verifies files on disk, not in your response. If a Write call is blocked or errors, STOP and report the error — do not claim success.

2. VERIFY BEFORE MARKING DONE. Before you update the task file's state field, use Read or a Bash `ls`/`cat` to confirm every Creates: path exists and every Modifies: path contains your change. If any file is missing or unchanged, the task is NOT done.

3. FLIP ACCEPTANCE CRITERIA BOXES. When marking the task DONE, flip every `- [ ]` in the `## Acceptance Criteria` section to `- [x]`. An unchecked box on a DONE task counts as an incomplete run — the audit will catch it.

4. NONCE PROOF IN REGISTERS. Update the task file's `## Registers` section with proof you read the file: include the current `checkpoint:` value from the frontmatter, a one-line summary of what was created/modified, and (if needed) the new nonce you generated for the next agent.

5. STATE TRANSITION. Only after steps 1–4 are complete, change the frontmatter `state:` field from PENDING (or current) to DONE. Workers cascade within a wave — you do not need to wait on an advisor to enter DONE; wave-gate review happens at the wave boundary.

6. DO NOT READ MAP.md OR CLAUDE.md. Your task file is self-contained. Hooks will block these reads — if you need a path or convention, it is already listed in the task file's `## Files` section.

7. REVISE AWARENESS. Read the task file's `## Registers` section. If it contains `REVISE round N` entries, the advisor previously rejected this task — the entries explain what was wrong. Address that feedback specifically before re-executing. A REVISE round N entry means you've already failed N-1 times; round 3+ triggers BLOCKED escalation, so fix the actual issue this round, don't just retry."""


_ADVISOR_PROMPT_TEMPLATE = """Review the following wave batch as ONE review pass. Each task file is self-contained.

Task files in this wave:
{task_list}

For EACH task file:
1. Read the task file.
2. Read every file listed in its ## Files section (both Creates and Modifies paths).
3. Evaluate that task against its Acceptance Criteria AND the project's coding discipline (functions ≤2 params, ≤20 lines, classes ≤3 public methods, type hints, no magic numbers, no swallowed exceptions).
4. Verify the task's state field is DONE and every acceptance checkbox is flipped to [x].

Return your verdict on the FIRST LINE of your response, applied to the WHOLE batch:
APPROVE - every task in the batch meets all criteria and discipline.
REVISE - at least one task has an issue.

If REVISE, the SECOND LINE of your response MUST be exactly:
FAILING TASKS: task_NNNa, task_NNNb, ...

List ONLY the task_ids that actually have issues — do NOT list passing tasks. The orchestrator parses this line to decide which tasks to re-dispatch. If you list every reviewed task, the entire wave reruns unnecessarily and wastes tokens.

Below the FAILING TASKS line, give per-task issue details keyed by task_id (e.g., "## task_814a: function X exceeds 20 lines")."""


def _build_advisor_prompt(task_paths: list[str]) -> str:
    """Return the wave-batch advisor prompt template."""
    task_list = "\n".join(f"- {p}" for p in task_paths)
    return _ADVISOR_PROMPT_TEMPLATE.format(task_list=task_list)


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
    cmd = [CLAUDE_CMD, "-p", prompt, "--model", model, "--permission-mode", "bypassPermissions"]
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


def dispatch_workers_parallel(requests: list[WorkerDispatchRequest]) -> list[DispatchResult]:
    """Dispatch multiple worker tasks in parallel, return results in request order.

    Uses ThreadPoolExecutor bounded by MAX_PARALLEL_WORKERS. Each submitted task
    calls dispatch_worker which spawns its own `claude -p` subprocess. Python's
    GIL is released while subprocess children execute, so concurrency is real
    wall-clock parallelism. Returns list of DispatchResult in the same order as
    the input requests.
    """
    if not requests:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
        futures = [executor.submit(dispatch_worker, req) for req in requests]
        return [f.result() for f in futures]


def dispatch_advisor(request: AdvisorDispatchRequest) -> DispatchResult:
    """Dispatch a wave-batch advisor review (always Opus)."""
    prompt = _build_advisor_prompt(request.task_paths)
    return _run_claude(prompt, ADVISOR_MODEL)


def dispatch_revise(request: ReviseDispatchRequest) -> DispatchResult:
    """Dispatch a REVISE round using the task's original dispatch role."""
    prompt = _build_revise_prompt(request)
    return _run_claude(prompt, MODEL_MAP.get(request.dispatch_role, "haiku"))
