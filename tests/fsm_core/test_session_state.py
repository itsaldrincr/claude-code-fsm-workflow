import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.fsm_core.session_state import (
    SessionState,
    SessionStateError,
    read_state,
    write_state,
)

SAMPLE_STATE = SessionState(
    current_phase="execute",
    active_wave=3,
    pipeline_stage="workers_running",
    last_updated="2026-04-08T12:00:00.000000Z",
    status="running",
)


def test_round_trip_byte_identical(tmp_path: Path) -> None:
    """AC4.1: write_state then read_state returns byte-identical SessionState."""
    write_state(tmp_path, SAMPLE_STATE)
    result = read_state(tmp_path)
    assert result == SAMPLE_STATE


def test_missing_file_returns_none(tmp_path: Path) -> None:
    """AC4.2: read_state on a workspace with no session_state.json returns None."""
    result = read_state(tmp_path)
    assert result is None


def test_crash_leaves_previous_intact(tmp_path: Path) -> None:
    """AC4.3: crash between tmp write and rename leaves previous state intact."""
    write_state(tmp_path, SAMPLE_STATE)

    updated_state = SessionState(
        current_phase="audit",
        active_wave=4,
        pipeline_stage="audit_running",
        last_updated="2026-04-08T13:00:00.000000Z",
        status="running",
    )

    with patch("os.replace", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError):
            write_state(tmp_path, updated_state)

    result = read_state(tmp_path)
    assert result == SAMPLE_STATE


def test_invalid_json_raises_session_state_error(tmp_path: Path) -> None:
    """read_state raises SessionStateError when JSON is malformed."""
    state_dir = tmp_path / ".claude"
    state_dir.mkdir(parents=True)
    (state_dir / "session_state.json").write_text("not-valid-json", encoding="utf-8")
    with pytest.raises(SessionStateError):
        read_state(tmp_path)


def test_missing_field_raises_session_state_error(tmp_path: Path) -> None:
    """read_state raises SessionStateError when a required field is absent."""
    state_dir = tmp_path / ".claude"
    state_dir.mkdir(parents=True)
    partial = {"current_phase": "execute", "active_wave": 1}
    (state_dir / "session_state.json").write_text(json.dumps(partial), encoding="utf-8")
    with pytest.raises(SessionStateError):
        read_state(tmp_path)


def test_negative_wave_raises_value_error() -> None:
    """SessionState.__post_init__ raises ValueError for active_wave < 0."""
    with pytest.raises(ValueError):
        SessionState(
            current_phase="idle",
            active_wave=-1,
            pipeline_stage="idle",
            last_updated="2026-04-08T00:00:00.000000Z",
            status="paused",
        )


def test_checkpoints_skipped_this_session_round_trip(tmp_path: Path) -> None:
    """Feature 6c: round-trip checkpoints_skipped_this_session list."""
    state = SessionState(
        current_phase="execute",
        active_wave=1,
        pipeline_stage="workers_running",
        last_updated="2026-04-08T12:00:00.000000Z",
        status="running",
        checkpoints_skipped_this_session=["task_999", "task_1000"],
    )
    write_state(tmp_path, state)
    result = read_state(tmp_path)
    assert result is not None
    assert result.checkpoints_skipped_this_session == ["task_999", "task_1000"]
