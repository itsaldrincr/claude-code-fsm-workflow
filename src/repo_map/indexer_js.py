from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.repo_map.models import FileIndex, Symbol

logger = logging.getLogger(__name__)

FUNCTION_RE: re.Pattern[str] = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)"
)
CLASS_RE: re.Pattern[str] = re.compile(
    r"^(?:export\s+)?(?:default\s+)?class\s+(\w+)"
)
CONST_RE: re.Pattern[str] = re.compile(
    r"^(?:export\s+)?const\s+(\w+)\s*="
)
IMPORT_RE: re.Pattern[str] = re.compile(
    r"^import\s+.*?from\s+['\"]([^'\"]+)['\"]"
)
EXPORT_RE: re.Pattern[str] = re.compile(
    r"^export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)"
)

_SUFFIX_TO_LANGUAGE = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
}


@dataclass
class _LineContext:
    """Carries a single line plus its 1-indexed number and all lines."""

    text: str
    lineno: int
    all_lines: List[str]


def _infer_language(path: Path) -> str:
    """Return language string inferred from file suffix."""
    return _SUFFIX_TO_LANGUAGE.get(path.suffix, "unknown")


def _find_block_end(ctx: _LineContext) -> int:
    """Return 1-indexed end line of the block starting at ctx.lineno."""
    if "{" not in ctx.text:
        return ctx.lineno
    for idx in range(ctx.lineno, len(ctx.all_lines)):
        if ctx.all_lines[idx].lstrip().startswith("}"):
            return idx + 1
    return ctx.lineno


def _scan_imports(lines: List[str]) -> List[str]:
    """Return all import source strings found at module top level."""
    imports: List[str] = []
    for line in lines:
        match = IMPORT_RE.match(line)
        if match:
            imports.append(match.group(1))
    return imports


def _scan_exports(lines: List[str]) -> List[str]:
    """Return all exported symbol names found at module top level."""
    exports: List[str] = []
    for line in lines:
        match = EXPORT_RE.match(line)
        if match:
            exports.append(match.group(1))
    return exports


def _scan_symbols(lines: List[str]) -> List[Symbol]:
    """Return Symbol objects for all top-level declarations."""
    symbols: List[Symbol] = []
    for lineno, text in enumerate(lines, start=1):
        ctx = _LineContext(text=text, lineno=lineno, all_lines=lines)
        result = _match_symbol(ctx)
        if result is not None:
            symbols.append(result)
    return symbols


def _match_symbol(ctx: _LineContext) -> Optional[Symbol]:
    """Return a Symbol if ctx.text matches a top-level declaration, else None."""
    for pattern, kind in (
        (FUNCTION_RE, "function"),
        (CLASS_RE, "class"),
        (CONST_RE, "const"),
    ):
        match = pattern.match(ctx.text)
        if match:
            end = _find_block_end(ctx)
            return Symbol(name=match.group(1), kind=kind, line=ctx.lineno, end_line=end)
    return None


def index_js(path: Path) -> FileIndex:
    """Read a JS/TS file and return a FileIndex with extracted symbols."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    language = _infer_language(path)
    symbols = _scan_symbols(lines)
    symbols.sort(key=lambda s: s.line)
    imports = _scan_imports(lines)
    exports = _scan_exports(lines)
    return FileIndex(
        path=str(path.resolve()),
        mtime=path.stat().st_mtime,
        line_count=len(lines),
        language=language,
        symbols=symbols,
        imports=imports,
        exports=exports,
    )
