"""Dispatch file indexing to language-specific backends."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import List

from src.repo_map.models import AgentSeen, FileIndex, IndexRequest, Symbol

logger = logging.getLogger(__name__)

KIND_FUNCTION = "function"
KIND_ASYNC_FUNCTION = "async_function"
KIND_CLASS = "class"
LANGUAGE_PYTHON = "python"
SUFFIX_PYTHON = ".py"


def _collect_symbols(body: list) -> List[Symbol]:
    """Extract top-level function, async function, and class symbols."""
    symbols: List[Symbol] = []
    for node in body:
        if isinstance(node, ast.FunctionDef):
            symbols.append(Symbol(node.name, KIND_FUNCTION, node.lineno, node.end_lineno))
        elif isinstance(node, ast.AsyncFunctionDef):
            symbols.append(Symbol(node.name, KIND_ASYNC_FUNCTION, node.lineno, node.end_lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(node.name, KIND_CLASS, node.lineno, node.end_lineno))
    return sorted(symbols, key=lambda s: s.line)


def _collect_imports(body: list) -> List[str]:
    """Extract top-level import names from Import and ImportFrom nodes."""
    imports: List[str] = []
    for node in body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend(f"{module}.{alias.name}" for alias in node.names)
    return imports


def index_python(path: Path) -> FileIndex:
    """Parse a Python file and return a FileIndex with symbols and imports."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    symbols = _collect_symbols(tree.body)
    imports = _collect_imports(tree.body)
    line_count = len(source.splitlines())
    return FileIndex(
        path=str(path.resolve()),
        mtime=path.stat().st_mtime,
        line_count=line_count,
        language=LANGUAGE_PYTHON,
        symbols=symbols,
        imports=imports,
        agent_seen=AgentSeen(ranges_read=[], outline_shown=False),
    )


def _is_python(request: IndexRequest) -> bool:
    """Return True if the request targets a Python file."""
    hint_matches = request.language_hint == LANGUAGE_PYTHON
    suffix_matches = Path(request.file_path).suffix == SUFFIX_PYTHON
    return hint_matches or suffix_matches


def index_file(request: IndexRequest) -> FileIndex:
    """Dispatch indexing to the correct language backend."""
    if _is_python(request):
        return index_python(Path(request.file_path))
    raise NotImplementedError(
        f"No indexer for language_hint={request.language_hint!r}, "
        f"suffix={Path(request.file_path).suffix!r}"
    )
