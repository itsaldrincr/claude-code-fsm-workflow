import dataclasses
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Phase = Literal["execute", "audit", "fix", "test", "close", "idle"]
PipelineStage = Literal[
    "workers_running", "workers_done",
    "audit_running", "audit_done",
    "fix_running", "fix_done",
    "test_running", "test_done",
    "closing", "closed", "idle",
]
Status = Literal["running", "paused", "blocked"]

CLAUDE_SUBDIR: str = ".claude"
SESSION_STATE_FILENAME: str = "session_state.json"
SESSION_STATE_RELPATH = Path(CLAUDE_SUBDIR) / SESSION_STATE_FILENAME

VALID_PHASES = {"execute", "audit", "fix", "test", "close", "idle"}
VALID_STAGES = {
    "workers_running", "workers_done",
    "audit_running", "audit_done",
    "fix_running", "fix_done",
    "test_running", "test_done",
    "closing", "closed", "idle",
}
VALID_STATUSES = {"running", "paused", "blocked"}
REQUIRED_FIELDS = {"current_phase", "active_wave", "pipeline_stage", "last_updated", "status"}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionState:
    """Immutable snapshot of the current pipeline state."""

    current_phase: Phase
    active_wave: int
    pipeline_stage: PipelineStage
    last_updated: str
    status: Status
    checkpoints_skipped_this_session: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if self.active_wave < 0:
            raise ValueError(f"active_wave must be >= 0, got {self.active_wave}")


class SessionStateError(RuntimeError):
    """Raised when session_state.json exists but is invalid JSON or fails schema."""


def state_path(workspace: Path) -> Path:
    """Return workspace / '.claude' / 'session_state.json'."""
    return workspace / SESSION_STATE_RELPATH


def read_state(workspace: Path) -> "SessionState | None":
    """Read session_state.json from workspace, return SessionState or None.

    Returns None if the file does not exist (expected first-run case).
    Raises SessionStateError if the file exists but cannot be parsed or
    fails schema validation.
    """
    path = state_path(workspace)
    if not path.exists():
        return None
    return _parse_state_file(path)


def write_state(workspace: Path, state: SessionState) -> None:
    """Atomically write state to workspace/.claude/session_state.json.

    Ensures workspace/.claude exists, serializes to a .tmp file,
    then os.replace for atomic POSIX rename.
    """
    path = state_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    payload = json.dumps(dataclasses.asdict(state), indent=2)
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)
    logger.debug("Wrote session state to %s", path)


def _coerce_checkpoints(raw: object, caller: str) -> list[str]:
    """Coerce checkpoints_skipped_this_session to list[str], logging on type mismatch."""
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return raw
    logger.warning("%s: checkpoints_skipped_this_session is %r; coercing to []", caller, raw)
    return []


def _parse_state_file(path: Path) -> SessionState:
    """Parse and validate session_state.json, raising SessionStateError on failure."""
    raw = path.read_text(encoding="utf-8")
    data = _decode_json(raw, path)
    _validate_fields(data, path)
    return SessionState(
        current_phase=data["current_phase"],
        active_wave=data["active_wave"],
        pipeline_stage=data["pipeline_stage"],
        last_updated=data["last_updated"],
        status=data["status"],
        checkpoints_skipped_this_session=_coerce_checkpoints(
            data.get("checkpoints_skipped_this_session", []), _parse_state_file.__name__
        ),
    )


def _decode_json(raw: str, path: Path) -> dict:
    """Decode JSON string, raising SessionStateError on parse failure."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SessionStateError(f"Invalid JSON in {path}: {exc}") from exc


def _validate_fields(data: dict, path: Path) -> None:
    """Validate that all required fields are present with correct types."""
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise SessionStateError(f"Missing fields in {path}: {missing}")
    _check_field_types(data, path)


def _check_field_types(data: dict, path: Path) -> None:
    """Validate field values are within allowed Literal sets."""
    if data["current_phase"] not in VALID_PHASES:
        raise SessionStateError(f"Invalid current_phase '{data['current_phase']}' in {path}")
    if data["pipeline_stage"] not in VALID_STAGES:
        raise SessionStateError(f"Invalid pipeline_stage '{data['pipeline_stage']}' in {path}")
    if data["status"] not in VALID_STATUSES:
        raise SessionStateError(f"Invalid status '{data['status']}' in {path}")
    if not isinstance(data["active_wave"], int):
        raise SessionStateError(f"active_wave must be int in {path}")
    if not isinstance(data["last_updated"], str):
        raise SessionStateError(f"last_updated must be str in {path}")
