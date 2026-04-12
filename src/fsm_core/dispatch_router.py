"""Dispatch backend routing for Claude-session-native transport only."""

from pathlib import Path

from src.fsm_core import claude_session_backend
from src.fsm_core.dispatch_contract import (
    AdvisorDispatchRequest,
    DispatchResult,
    ReviseDispatchRequest,
    WorkerDispatchRequest,
)
from src.fsm_core.startup_checks import resolve_dispatch_mode


def dispatch_workers_parallel(
    requests: list[WorkerDispatchRequest], *, dispatch_mode: str | None = None, workspace: Path | None = None
) -> list[DispatchResult]:
    """Enqueue worker intents in claude_session mode."""
    _ = resolve_dispatch_mode(dispatch_mode)
    base = workspace if workspace is not None else Path.cwd()
    return claude_session_backend.dispatch_workers_parallel(workspace=base, requests=requests)


def dispatch_advisor(
    request: AdvisorDispatchRequest, *, dispatch_mode: str | None = None, workspace: Path | None = None
) -> DispatchResult:
    """Enqueue advisor intent in claude_session mode."""
    _ = resolve_dispatch_mode(dispatch_mode)
    base = workspace if workspace is not None else Path.cwd()
    return claude_session_backend.dispatch_advisor(workspace=base, request=request)


def dispatch_revise(
    request: ReviseDispatchRequest, *, dispatch_mode: str | None = None, workspace: Path | None = None
) -> DispatchResult:
    """Enqueue revise intent in claude_session mode."""
    _ = resolve_dispatch_mode(dispatch_mode)
    base = workspace if workspace is not None else Path.cwd()
    return claude_session_backend.dispatch_revise(workspace=base, request=request)
