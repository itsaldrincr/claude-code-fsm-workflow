#!/usr/bin/env python3
"""PreToolUse hook for Read: enrich with outline, redirect large files, or elide overlap."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.repo_map.models import AgentSeen, FileIndex, RepoMap
from src.repo_map.store import get_or_index, load_map, save_map, StoreRequest

DEFAULT_LARGE_FILE_THRESHOLD: int = 500
SYMBOL_SUMMARY_MAX_COUNT: int = 3
CONFIG_RELATIVE_PATH: Path = Path.home() / ".claude/hooks/repo-map/config.json"
LOG_DIR: Path = Path.home() / ".claude/hooks/repo-map/log"
OUTLINE_OPEN: str = "<repo-map-outline>"
OUTLINE_CLOSE: str = "</repo-map-outline>"
HOOK_EVENT_NAME: str = "PreToolUse"
ELISION_TEMPLATE: str = "[lines {start}-{end} already in context, omitted]"


@dataclass
class HookEvent:
    """Parsed fields from a Claude Code PreToolUse hook event."""

    file_path: Path
    offset: Optional[int]
    limit: Optional[int]
    project_root: Path


@dataclass
class DispatchContext:
    """Gathered state for dispatching a hook event branch."""

    event: HookEvent
    repo_map: RepoMap
    threshold: int


@dataclass
class OverlapQuery:
    """Parameters for checking or computing range overlap."""

    req_start: int
    req_end: int
    seen: List[Tuple[int, int]]


@dataclass
class HookResponse:
    """Data for building the hookSpecificOutput wrapper."""

    decision: str
    reason: str
    context: str


def _get_logger() -> logging.Logger:
    """Return a logger that writes to LOG_DIR if it exists, else a no-op logger."""
    log = logging.getLogger(__name__)
    if not LOG_DIR.exists():
        log.addHandler(logging.NullHandler())
        return log
    handler = logging.FileHandler(LOG_DIR / "pre_read.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return log


logger = _get_logger()


def _load_threshold() -> int:
    """Load large_file_threshold from config.json, fallback to DEFAULT."""
    if not CONFIG_RELATIVE_PATH.exists():
        return DEFAULT_LARGE_FILE_THRESHOLD
    try:
        raw = json.loads(CONFIG_RELATIVE_PATH.read_text(encoding="utf-8"))
        return int(raw.get("large_file_threshold", DEFAULT_LARGE_FILE_THRESHOLD))
    except Exception:
        logger.exception("Failed reading config; using default threshold")
        return DEFAULT_LARGE_FILE_THRESHOLD


def _parse_event(raw: str) -> HookEvent:
    """Parse hook event JSON from stdin into a HookEvent."""
    data: Dict[str, Any] = json.loads(raw)
    tool_input: Dict[str, Any] = data.get("toolInput", data.get("tool_input", {}))
    file_path_str: str = tool_input.get("file_path", "")
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    project_root_str: str = data.get("cwd", str(Path.cwd()))
    return HookEvent(
        file_path=Path(file_path_str),
        offset=int(offset) if offset is not None else None,
        limit=int(limit) if limit is not None else None,
        project_root=Path(project_root_str),
    )


def _emit_response(resp: HookResponse) -> None:
    """Write the hookSpecificOutput wrapper JSON to stdout."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": resp.decision,
            "permissionDecisionReason": resp.reason,
            "additionalContext": resp.context,
        }
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def _format_outline(file_index: FileIndex) -> str:
    """Build the repo-map outline XML string from a FileIndex."""
    lines: List[str] = [OUTLINE_OPEN]
    for sym in file_index.symbols:
        lines.append(f"  {sym.name} [{sym.line}-{sym.end_line}] ({sym.kind})")
    lines.append(OUTLINE_CLOSE)
    return "\n".join(lines)


def _symbol_summary(file_index: FileIndex) -> str:
    """Build a short symbol list string for the deny directive."""
    parts = [f"{s.name} [{s.line}-{s.end_line}]" for s in file_index.symbols[:SYMBOL_SUMMARY_MAX_COUNT]]
    return ", ".join(parts)


def _build_deny_reason(file_index: FileIndex) -> str:
    """Build the permissionDecisionReason for the large-file deny branch."""
    if not file_index.symbols:
        return "File is large; use offset and limit to read specific sections."
    first = file_index.symbols[0]
    summary = _symbol_summary(file_index)
    return (
        f"Re-call Read with offset={first.line} limit={first.end_line - first.line + 1}"
        f" to see {first.name}() (lines {first.line}-{first.end_line})."
        f" Available symbols: {summary}."
    )


def _ranges_overlap(query: OverlapQuery) -> bool:
    """Return True if the requested range overlaps any seen range."""
    for start, end in query.seen:
        if query.req_start <= end and query.req_end >= start:
            return True
    return False


def _compute_delta(query: OverlapQuery) -> str:
    """Compute elision marker for first overlapping range in query.seen."""
    for start, end in query.seen:
        overlap_start = max(query.req_start, start)
        overlap_end = min(query.req_end, end)
        if overlap_start <= overlap_end:
            return ELISION_TEMPLATE.format(start=overlap_start, end=overlap_end)
    return ""


def _ensure_agent_seen(file_index: FileIndex) -> AgentSeen:
    """Return existing AgentSeen or create a fresh one."""
    if file_index.agent_seen is None:
        file_index.agent_seen = AgentSeen()
    return file_index.agent_seen


def _mark_outline_shown(ctx: DispatchContext, file_index: FileIndex) -> None:
    """Set outline_shown=True and persist the map."""
    seen = _ensure_agent_seen(file_index)
    seen.outline_shown = True
    save_map(ctx.repo_map)


def _handle_first_read(ctx: DispatchContext, file_index: FileIndex) -> None:
    """Branch (a)/(b): emit outline and mark outline_shown."""
    outline = _format_outline(file_index)
    _mark_outline_shown(ctx, file_index)
    _emit_response(HookResponse(decision="allow", reason="", context=outline))


def _handle_overlap(ctx: DispatchContext, file_index: FileIndex) -> None:
    """Branch (c): emit elision marker for overlapping range."""
    seen = _ensure_agent_seen(file_index)
    offset = ctx.event.offset or 1
    limit = ctx.event.limit if ctx.event.limit is not None else file_index.line_count
    req_end = offset + limit - 1
    query = OverlapQuery(req_start=offset, req_end=req_end, seen=seen.ranges_read)
    delta = _compute_delta(query)
    _emit_response(HookResponse(decision="allow", reason="", context=delta))


def _handle_large_unbounded(ctx: DispatchContext, file_index: FileIndex) -> None:
    """Branch (d): deny unbounded read of large file, return outline + directive."""
    reason = _build_deny_reason(file_index)
    outline = _format_outline(file_index)
    _emit_response(HookResponse(decision="deny", reason=reason, context=outline))


def _is_unbounded_large(ctx: DispatchContext, file_index: FileIndex) -> bool:
    """Return True if event is unbounded AND file exceeds threshold."""
    is_unbounded = ctx.event.offset is None and ctx.event.limit is None
    return is_unbounded and file_index.line_count > ctx.threshold


def _needs_outline(file_index: FileIndex) -> bool:
    """Return True if outline has not been shown yet."""
    if file_index.agent_seen is None:
        return True
    return not file_index.agent_seen.outline_shown


def _has_overlap(ctx: DispatchContext, file_index: FileIndex) -> bool:
    """Return True if request overlaps previously seen ranges."""
    if file_index.agent_seen is None:
        return False
    if not file_index.agent_seen.ranges_read:
        return False
    offset = ctx.event.offset or 1
    limit = ctx.event.limit if ctx.event.limit is not None else file_index.line_count
    req_end = offset + limit - 1
    query = OverlapQuery(req_start=offset, req_end=req_end, seen=file_index.agent_seen.ranges_read)
    return _ranges_overlap(query)


def _dispatch(ctx: DispatchContext) -> None:
    """Route to the correct projection branch based on file state."""
    resolved = ctx.event.file_path.resolve()
    store_req = StoreRequest(repo_map=ctx.repo_map, file_path=str(resolved))
    file_index = get_or_index(store_req)

    if _needs_outline(file_index):
        _handle_first_read(ctx, file_index)
        return

    if _is_unbounded_large(ctx, file_index):
        _handle_large_unbounded(ctx, file_index)
        return

    if _has_overlap(ctx, file_index):
        _handle_overlap(ctx, file_index)
        return

    # Branch (e): pass through — no output


def main() -> None:
    """Entry point: parse stdin, dispatch, emit response."""
    raw = sys.stdin.read()
    try:
        event = _parse_event(raw)
    except Exception:
        logger.exception("Failed to parse hook event; passing through")
        return

    repo_map = load_map(event.project_root)
    threshold = _load_threshold()
    ctx = DispatchContext(event=event, repo_map=repo_map, threshold=threshold)

    try:
        _dispatch(ctx)
    except Exception:
        logger.exception("Hook dispatch failed; passing through")


if __name__ == "__main__":
    main()
