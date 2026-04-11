"""Atomic JSON sidecar store: load, save, and get-or-index RepoMap entries."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.repo_map.models import (
    AgentSeen,
    FileIndex,
    IndexRequest,
    RepoMap,
    StoreRequest,
    Symbol,
)
from src.repo_map.indexer import index_file
from src.repo_map.indexer_js import index_js

logger = logging.getLogger(__name__)

SIDECAR_RELATIVE_PATH = Path(".claude/repo-map.json")
SUPPORTED_PYTHON_SUFFIXES: frozenset = frozenset({".py"})
SUPPORTED_JS_SUFFIXES: frozenset = frozenset({".js", ".jsx", ".ts", ".tsx"})
INVALIDATED_MTIME = -1.0


def load_map(project_root: Path) -> RepoMap:
    """Load the sidecar JSON from project_root; return empty RepoMap if missing."""
    sidecar = project_root.resolve() / SIDECAR_RELATIVE_PATH
    if not sidecar.exists():
        return RepoMap(project_root=str(project_root.resolve()), entries={})
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    return _rebuild_repo_map(raw)


def save_map(repo_map: RepoMap) -> None:
    """Atomically write repo_map to its sidecar JSON file via temp+rename."""
    sidecar = Path(repo_map.project_root) / SIDECAR_RELATIVE_PATH
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataclasses.asdict(repo_map), indent=2)
    _atomic_write(sidecar, payload)


def get_or_index(request: StoreRequest) -> FileIndex:
    """Return a cached FileIndex or re-index the file and cache the result."""
    file_path = Path(request.file_path).resolve()
    key = str(file_path)
    cached = request.repo_map.entries.get(key)
    if _is_cache_valid(cached, file_path):
        return cached  # type: ignore[return-value]
    entry = _dispatch_index(file_path)
    request.repo_map.entries[key] = entry
    save_map(request.repo_map)
    return entry


# ── private helpers ────────────────────────────────────────────────────────────


def _atomic_write(path: Path, payload: str) -> None:
    """Write payload to path atomically using a temp file + os.rename."""
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.rename(tmp_path, path)
    except Exception:
        logger.exception("Atomic write failed; temp file may remain at %s", tmp_path)
        raise


def _is_cache_valid(entry: Optional[FileIndex], file_path: Path) -> bool:
    """Return True if entry exists, mtime is not invalidated, and matches disk."""
    if entry is None:
        return False
    if entry.mtime == INVALIDATED_MTIME:
        return False
    try:
        return entry.mtime == file_path.stat().st_mtime
    except FileNotFoundError:
        return False


def _dispatch_index(file_path: Path) -> FileIndex:
    """Dispatch indexing to the correct backend by file suffix."""
    suffix = file_path.suffix
    if suffix in SUPPORTED_PYTHON_SUFFIXES:
        return _index_python(file_path)
    if suffix in SUPPORTED_JS_SUFFIXES:
        return _index_js(file_path)
    return _stub_file_index(file_path)


def _index_python(file_path: Path) -> FileIndex:
    """Index a Python file via the indexer backend."""
    return index_file(IndexRequest(file_path=str(file_path)))


def _index_js(file_path: Path) -> FileIndex:
    """Index a JS/TS file via the indexer_js backend."""
    return index_js(file_path)


def _stub_file_index(file_path: Path) -> FileIndex:
    """Build a minimal FileIndex stub for unsupported file types."""
    return FileIndex(
        path=str(file_path),
        mtime=file_path.stat().st_mtime,
        line_count=0,
        language="unknown",
        symbols=[],
        imports=[],
        exports=[],
    )


def _rebuild_symbol(raw: dict) -> Symbol:
    """Reconstruct a Symbol from a plain dict."""
    return Symbol(
        name=raw["name"],
        kind=raw["kind"],
        line=raw["line"],
        end_line=raw["end_line"],
    )


def _rebuild_agent_seen(raw: Optional[dict]) -> Optional[AgentSeen]:
    """Reconstruct an AgentSeen from a plain dict, or return None."""
    if raw is None:
        return None
    ranges: List[Tuple[int, int]] = [tuple(r) for r in raw.get("ranges_read", [])]  # type: ignore[misc]
    return AgentSeen(ranges_read=ranges, outline_shown=raw.get("outline_shown", False))


def _rebuild_file_index(raw: dict) -> FileIndex:
    """Reconstruct a FileIndex from a plain dict."""
    symbols = [_rebuild_symbol(s) for s in raw.get("symbols", [])]
    agent_seen = _rebuild_agent_seen(raw.get("agent_seen"))
    return FileIndex(
        path=raw["path"],
        mtime=raw["mtime"],
        line_count=raw["line_count"],
        language=raw["language"],
        symbols=symbols,
        imports=raw.get("imports", []),
        exports=raw.get("exports", []),
        agent_seen=agent_seen,
    )


def _rebuild_entries(raw_entries: Dict[str, dict]) -> Dict[str, FileIndex]:
    """Reconstruct all FileIndex entries from a raw dict."""
    return {key: _rebuild_file_index(val) for key, val in raw_entries.items()}


def _rebuild_repo_map(raw: dict) -> RepoMap:
    """Reconstruct a RepoMap from a plain dict."""
    entries = _rebuild_entries(raw.get("entries", {}))
    return RepoMap(project_root=raw["project_root"], entries=entries)
