import logging
import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

WRITE_PID_MODE: int = 0o644
MS_PER_SECOND: int = 1000


@dataclass(frozen=True)
class LockConfig:
    """Configuration for map_lock acquisition behavior."""

    max_retries: int = 10
    retry_delay_ms: int = 200
    stale_lock_seconds: int = 10
    jitter_max_ms: int = 50

    def __post_init__(self) -> None:
        """Validate all fields are positive integers."""
        for field_name in ("max_retries", "retry_delay_ms", "stale_lock_seconds", "jitter_max_ms"):
            value = getattr(self, field_name)
            if value <= 0:
                raise ValueError(f"{field_name} must be positive, got {value}")


class LockTimeoutError(RuntimeError):
    """Raised when map_lock cannot be acquired within max_retries."""


class LockAcquisitionError(RuntimeError):
    """Raised for unexpected OS errors (permission denied, etc)."""


def _try_acquire(lock_path: Path) -> bool:
    """Single O_EXCL attempt to create lockfile. Returns True on success, False on conflict."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(lock_path), flags, WRITE_PID_MODE)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError as exc:
        raise LockAcquisitionError(f"Unexpected OS error acquiring lock: {exc}") from exc


def _is_stale(lock_path: Path, stale_seconds: int) -> bool:
    """Return True if lockfile mtime is older than stale_seconds."""
    try:
        mtime = lock_path.stat().st_mtime
        return (time.time() - mtime) > stale_seconds
    except FileNotFoundError:
        return False


def _reclaim_stale(lock_path: Path) -> None:
    """Unlink a stale lockfile. Logs warning on failure."""
    try:
        lock_path.unlink()
        logger.warning("Reclaimed stale lockfile: %s", lock_path)
    except FileNotFoundError:
        logger.debug("Lockfile already gone: %s", lock_path)
    except OSError as exc:
        logger.warning("Failed to reclaim stale lockfile %s: %s", lock_path, exc)


def _sleep_with_jitter(config: LockConfig) -> None:
    """Sleep retry_delay_ms plus random jitter up to jitter_max_ms."""
    jitter = random.uniform(0, config.jitter_max_ms / MS_PER_SECOND)
    delay = config.retry_delay_ms / MS_PER_SECOND
    time.sleep(delay + jitter)


def _release(lock_path: Path) -> None:
    """Unlink lockfile on exit. Logs but does not raise on failure."""
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Failed to release lockfile %s: %s", lock_path, exc)


@contextmanager
def map_lock(map_path: Path, config: LockConfig = LockConfig()) -> Iterator[None]:
    """Acquire an exclusive lock on map_path + '.lock'. Context manager.

    On entry: repeatedly attempts os.open with O_CREAT|O_EXCL|O_WRONLY.
    Writes the current PID into the lockfile.
    On FileExistsError: if lockfile mtime > stale_lock_seconds, unlink and retry.
    Otherwise sleep retry_delay_ms + jitter and retry.
    After max_retries failures: raise LockTimeoutError.

    On exit (success or exception): unlink lockfile (silent on failure).

    Raises:
        LockTimeoutError: max_retries exhausted.
        LockAcquisitionError: unexpected OS error (e.g. permission denied).
    """
    lock_path = Path(str(map_path) + ".lock")
    # map_tmp_path is the atomic-write staging file used by callers (map_io.py).
    # map_lock owns its cleanup on exception to satisfy AC1.3: no orphaned .tmp
    # files after a crash inside the lock body. This coupling is explicitly
    # specified in the manifest §2 clarification on Item 1 lock behavior.
    map_tmp_path = Path(str(map_path) + ".tmp")
    _acquire_with_retries(lock_path, config)
    try:
        yield
    except BaseException:
        _release(map_tmp_path)
        raise
    finally:
        _release(lock_path)


def _acquire_with_retries(lock_path: Path, config: LockConfig) -> None:
    """Attempt lock acquisition up to max_retries times."""
    for attempt in range(config.max_retries):
        result = _try_acquire(lock_path)
        if result:
            return
        if _is_stale(lock_path, config.stale_lock_seconds):
            _reclaim_stale(lock_path)
            continue
        logger.debug("Lock busy, attempt %d/%d", attempt + 1, config.max_retries)
        _sleep_with_jitter(config)
    raise LockTimeoutError(
        f"Could not acquire lock on {lock_path} after {config.max_retries} retries"
    )
