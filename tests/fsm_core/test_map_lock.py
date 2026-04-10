import os
import threading
import time
from pathlib import Path

import pytest

from src.fsm_core.map_lock import LockConfig, LockTimeoutError, map_lock

THREAD_COUNT: int = 10
STALE_AGE_SECONDS: float = 20.0
FAST_CONFIG = LockConfig(max_retries=10, retry_delay_ms=50, stale_lock_seconds=10, jitter_max_ms=10)


def _append_line(map_path: Path, line: str) -> None:
    """Acquire lock and append a line to the file under lock."""
    with map_lock(map_path, FAST_CONFIG):
        with open(map_path, "a") as fh:
            fh.write(line + "\n")


def test_concurrent_writers_serialize(tmp_path: Path) -> None:
    """AC1.1: 10 concurrent writers each append one line; expect exactly 10 lines."""
    shared_file = tmp_path / "MAP.md"
    shared_file.touch()

    threads = [
        threading.Thread(target=_append_line, args=(shared_file, f"line_{i}"))
        for i in range(THREAD_COUNT)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = shared_file.read_text().splitlines()
    assert len(lines) == THREAD_COUNT, f"Expected {THREAD_COUNT} lines, got {len(lines)}"


def test_stale_lock_reclaimed(tmp_path: Path) -> None:
    """AC1.2: A lockfile older than stale_lock_seconds is reclaimed and acquisition succeeds."""
    map_path = tmp_path / "MAP.md"
    map_path.touch()
    lock_path = Path(str(map_path) + ".lock")

    lock_path.write_text("99999")
    stale_time = time.time() - STALE_AGE_SECONDS
    os.utime(str(lock_path), (stale_time, stale_time))

    acquired = False
    with map_lock(map_path, FAST_CONFIG):
        acquired = True
        assert lock_path.exists()

    assert acquired, "map_lock should have succeeded after reclaiming stale lock"
    assert not lock_path.exists(), "lockfile must be cleaned up after context exit"


def test_exception_cleans_lockfile_and_tmp(tmp_path: Path) -> None:
    """AC1.3: Exception inside with-body leaves no lockfile and no .tmp file."""
    map_path = tmp_path / "MAP.md"
    map_path.touch()
    lock_path = Path(str(map_path) + ".lock")
    tmp_file = Path(str(map_path) + ".tmp")

    with pytest.raises(RuntimeError, match="simulated crash"):
        with map_lock(map_path, FAST_CONFIG):
            tmp_file.write_text("partial write")
            raise RuntimeError("simulated crash")

    assert not lock_path.exists(), "lockfile must not exist after exception"
    assert not tmp_file.exists(), ".tmp file must be cleaned up by map_lock on exception"


def test_lock_timeout_raises(tmp_path: Path) -> None:
    """LockTimeoutError is raised when lock cannot be acquired after max_retries."""
    map_path = tmp_path / "MAP.md"
    map_path.touch()
    lock_path = Path(str(map_path) + ".lock")
    lock_path.write_text("99999")

    tight_config = LockConfig(max_retries=2, retry_delay_ms=10, stale_lock_seconds=3600, jitter_max_ms=5)
    with pytest.raises(LockTimeoutError):
        with map_lock(map_path, tight_config):
            pass

    lock_path.unlink(missing_ok=True)
