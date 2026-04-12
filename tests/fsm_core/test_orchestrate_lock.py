import os
import time
from pathlib import Path

from src.fsm_core.orchestrate_lock import ORCHESTRATE_LOCK_PATH, acquire_orchestrate_lock


def test_acquire_then_release(tmp_path: Path) -> None:
    """AC1: Lock file created on entry, removed on exit."""
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        lock_path = Path(ORCHESTRATE_LOCK_PATH)

        assert not lock_path.exists(), "Lock should not exist initially"

        with acquire_orchestrate_lock():
            assert lock_path.exists(), "Lock should be created on context entry"

        assert not lock_path.exists(), "Lock should be removed on context exit"
    finally:
        os.chdir(original_cwd)


def test_second_acquisition_blocks(tmp_path: Path) -> None:
    """AC2: Second acquisition fails and does not raise with fresh lock."""
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        lock_path = Path(ORCHESTRATE_LOCK_PATH)

        with acquire_orchestrate_lock():
            assert lock_path.exists(), "First acquisition should hold lock"
            initial_mtime = lock_path.stat().st_mtime

            with acquire_orchestrate_lock():
                current_mtime = lock_path.stat().st_mtime
                assert (
                    current_mtime == initial_mtime
                ), "Second context should not have updated lock mtime"

        assert not lock_path.exists(), "Lock should be cleaned up after outer context"
    finally:
        os.chdir(original_cwd)


def test_stale_lock_reclaimed(tmp_path: Path) -> None:
    """AC3: Pre-written stale lock file is reclaimed and acquisition succeeds."""
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        lock_path = Path(ORCHESTRATE_LOCK_PATH)

        lock_path.write_text("99999")
        stale_time = time.time() - 20.0
        os.utime(str(lock_path), (stale_time, stale_time))

        is_acquired = False
        with acquire_orchestrate_lock():
            is_acquired = True
            assert lock_path.exists(), "Lock should exist during context"

        assert is_acquired, "Should have acquired lock after stale reclaim"
        assert not lock_path.exists(), "Lock should be cleaned up after context exit"
    finally:
        os.chdir(original_cwd)
