"""Context manager for orchestrate.py lock acquisition."""

import contextlib
from pathlib import Path
from typing import Iterator

from src.config import ORCHESTRATE_LOCK_PATH
from src.fsm_core.map_lock import (
    LockConfig,
    _is_stale,
    _reclaim_stale,
    _release,
    _try_acquire,
)


@contextlib.contextmanager
def acquire_orchestrate_lock() -> Iterator[None]:
    """Acquire exclusive lock on orchestrate process. Context manager."""
    config = LockConfig()
    lock_path = Path(ORCHESTRATE_LOCK_PATH)
    is_holding = False
    try:
        is_holding = _try_acquire(lock_path)
        if not is_holding:
            if _is_stale(lock_path, config.stale_lock_seconds):
                _reclaim_stale(lock_path)
                is_holding = _try_acquire(lock_path)
                if not is_holding:
                    raise RuntimeError("orchestrate_lock: could not acquire after stale reclaim")
        yield
    finally:
        if is_holding:
            _release(lock_path)
