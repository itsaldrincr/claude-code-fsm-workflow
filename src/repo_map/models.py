from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ALLOWED_SYMBOL_KINDS = {"function", "async_function", "class", "const", "export"}
ALLOWED_LANGUAGES = {"python", "javascript", "typescript", "unknown"}
MIN_LINE_NUMBER = 1
MIN_LINE_COUNT = 0


def _validate_symbol_fields(name: str, kind: str) -> None:
    """Raise ValueError if symbol name or kind is invalid."""
    if not name:
        raise ValueError("Symbol.name must be non-empty")
    if kind not in ALLOWED_SYMBOL_KINDS:
        raise ValueError(f"Symbol.kind must be one of {ALLOWED_SYMBOL_KINDS}, got {kind!r}")


def _validate_symbol_lines(line: int, end_line: int) -> None:
    """Raise ValueError if symbol line numbers are invalid."""
    if line < MIN_LINE_NUMBER:
        raise ValueError(f"Symbol.line must be >= {MIN_LINE_NUMBER}, got {line}")
    if end_line < line:
        raise ValueError(f"Symbol.end_line must be >= line ({line}), got {end_line}")


def _validate_file_index_path(path: str) -> None:
    """Raise ValueError if path is not absolute."""
    if not Path(path).is_absolute():
        raise ValueError(f"FileIndex.path must be absolute, got {path!r}")


def _validate_file_index_language(language: str) -> None:
    """Raise ValueError if language is not in allowed set."""
    if language not in ALLOWED_LANGUAGES:
        raise ValueError(f"FileIndex.language must be one of {ALLOWED_LANGUAGES}, got {language!r}")


def _validate_file_index_line_count(line_count: int) -> None:
    """Raise ValueError if line_count is negative."""
    if line_count < MIN_LINE_COUNT:
        raise ValueError(f"FileIndex.line_count must be >= {MIN_LINE_COUNT}, got {line_count}")


def _validate_symbols_sorted(symbols: List[Symbol]) -> None:
    """Raise ValueError if symbols are not sorted by line number."""
    for i in range(1, len(symbols)):
        if symbols[i].line < symbols[i - 1].line:
            raise ValueError(
                f"FileIndex.symbols must be sorted by line; "
                f"symbol at index {i} has line {symbols[i].line} < {symbols[i - 1].line}"
            )


def _validate_repo_map_root(project_root: str) -> None:
    """Raise ValueError if project_root is not absolute."""
    if not Path(project_root).is_absolute():
        raise ValueError(f"RepoMap.project_root must be absolute, got {project_root!r}")


def _validate_repo_map_entries(project_root: str, entries: Dict[str, FileIndex]) -> None:
    """Raise ValueError if any entry key does not match its FileIndex.path."""
    for key, file_index in entries.items():
        if key != file_index.path:
            raise ValueError(
                f"RepoMap.entries key {key!r} does not match FileIndex.path {file_index.path!r}"
            )


@dataclass
class Symbol:
    """Represents a named code symbol within a file."""

    name: str
    kind: str
    line: int
    end_line: int

    def __post_init__(self) -> None:
        """Validate all Symbol fields."""
        _validate_symbol_fields(self.name, self.kind)
        _validate_symbol_lines(self.line, self.end_line)


@dataclass
class AgentSeen:
    """Tracks which parts of a file have been shown to an agent."""

    ranges_read: List[Tuple[int, int]] = field(default_factory=list)
    outline_shown: bool = False


@dataclass
class FileIndex:
    """Structural index for a single source file."""

    path: str
    mtime: float
    line_count: int
    language: str
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    agent_seen: Optional[AgentSeen] = None

    def __post_init__(self) -> None:
        """Validate all FileIndex fields."""
        _validate_file_index_path(self.path)
        _validate_file_index_line_count(self.line_count)
        _validate_file_index_language(self.language)
        _validate_symbols_sorted(self.symbols)


@dataclass
class RepoMap:
    """Top-level index mapping file paths to their FileIndex entries."""

    project_root: str
    entries: Dict[str, FileIndex] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate project_root and entries consistency."""
        _validate_repo_map_root(self.project_root)
        _validate_repo_map_entries(self.project_root, self.entries)


@dataclass
class IndexRequest:
    """Request to index a single file."""

    file_path: str
    language_hint: str = "unknown"


@dataclass
class StoreRequest:
    """Request to persist a RepoMap to disk."""

    repo_map: RepoMap
    file_path: str
