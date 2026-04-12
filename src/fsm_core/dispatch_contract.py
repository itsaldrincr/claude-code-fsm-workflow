"""Transport-agnostic dispatch request/result contracts."""

from dataclasses import dataclass


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
    """Result from a dispatch backend."""

    exit_code: int
    stdout: str
    stderr: str

