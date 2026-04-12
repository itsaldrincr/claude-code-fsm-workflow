"""Advisor verdict caching for wave gates.

Content-hashes wave inputs (prompt version + model + task paths + file hashes)
to avoid redundant bug-scanner dispatch on identical wave configurations.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


ADVISOR_PROMPT_VERSION: int = 1
"""Bump on every bug-scanner system prompt change."""


@dataclass(frozen=True, slots=True)
class WaveHashInput:
    """Inputs to the wave hash computation."""

    prompt_version: int
    """ADVISOR_PROMPT_VERSION at dispatch time."""

    model: str
    """Model used by bug-scanner (e.g. 'claude-opus-4')."""

    task_paths: tuple[str, ...]
    """Sorted task file paths."""

    file_hashes: tuple[tuple[str, str], ...]
    """Sorted (file_path, sha256_digest) pairs."""


@dataclass(frozen=True, slots=True)
class CachedVerdict:
    """Cached advisor verdict for a wave."""

    wave_hash: str
    """SHA256 hex digest of WaveHashInput."""

    verdict: str
    """'APPROVE' (only verdicts stored; REVISE never cached)."""

    timestamp_iso: str
    """ISO 8601 timestamp of verdict creation."""

    task_ids: tuple[str, ...]
    """Sorted task IDs reviewed in this wave."""

    schema_version: int
    """Cache schema version for migration."""


def compute_wave_hash(wave_input: WaveHashInput) -> str:
    """Compute deterministic SHA256 hash of wave inputs.

    Args:
        wave_input: WaveHashInput with version, model, paths, file hashes.

    Returns:
        Hex digest of canonical JSON serialization.
    """
    canonical = {
        "prompt_version": wave_input.prompt_version,
        "model": wave_input.model,
        "task_paths": list(wave_input.task_paths),
        "file_hashes": [list(pair) for pair in wave_input.file_hashes],
    }
    serialized = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _parse_cached_verdict(raw: dict) -> CachedVerdict | None:
    """Parse cached verdict from JSON dict.

    Args:
        raw: Dictionary loaded from cache file JSON.

    Returns:
        Parsed CachedVerdict or None if parse error.
    """
    try:
        return CachedVerdict(
            wave_hash=raw["wave_hash"],
            verdict=raw["verdict"],
            timestamp_iso=raw["timestamp_iso"],
            task_ids=tuple(raw["task_ids"]),
            schema_version=raw["schema_version"],
        )
    except (KeyError, TypeError):
        return None


def lookup_verdict(wave_hash: str, cache_dir: Path) -> CachedVerdict | None:
    """Look up a cached verdict by wave hash.

    Args:
        wave_hash: SHA256 hex digest of WaveHashInput.
        cache_dir: Directory containing cached verdict JSON files.

    Returns:
        Parsed CachedVerdict or None if file missing or parse error.
    """
    cache_file = cache_dir / f"{wave_hash}.json"
    if not cache_file.exists():
        return None
    try:
        with cache_file.open("r") as f:
            data = json.load(f)
        return _parse_cached_verdict(data)
    except (OSError, json.JSONDecodeError):
        return None


def _atomic_json_write(path: Path, payload: dict) -> None:
    """Atomically write JSON to file using temp file + rename.

    Args:
        path: Target file path.
        payload: Dictionary to serialize as JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def _verdict_to_dict(entry: CachedVerdict) -> dict[str, object]:
    """Serialize a CachedVerdict to a JSON-ready dict."""
    return {
        "wave_hash": entry.wave_hash,
        "verdict": entry.verdict,
        "timestamp_iso": entry.timestamp_iso,
        "task_ids": list(entry.task_ids),
        "schema_version": entry.schema_version,
    }


def store_verdict(entry: CachedVerdict, cache_dir: Path) -> bool:
    """Store a cached APPROVE verdict to disk; reject REVISE."""
    if entry.verdict != "APPROVE":
        return False
    cache_file = cache_dir / f"{entry.wave_hash}.json"
    _atomic_json_write(cache_file, _verdict_to_dict(entry))
    return True


def clear_cache(cache_dir: Path) -> int:
    """Delete all cached verdict files.

    Args:
        cache_dir: Directory containing cache files.

    Returns:
        Count of files deleted.
    """
    if not cache_dir.exists():
        return 0
    count = 0
    for cache_file in cache_dir.glob("*.json"):
        if cache_file.is_file():
            cache_file.unlink()
            count += 1
    return count
