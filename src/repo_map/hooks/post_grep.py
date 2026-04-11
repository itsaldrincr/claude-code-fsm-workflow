#!/usr/bin/env python3
"""PostToolUse on Grep: annotate each hit with its enclosing symbol via additionalContext."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.repo_map.models import FileIndex, RepoMap
from src.repo_map.store import StoreRequest, get_or_index, load_map, save_map

logger = logging.getLogger(__name__)

MODULE_LEVEL_LABEL = "[at module level]"
HOOK_EVENT_NAME = "PostToolUse"
SPLIT_MAX_COLONS = 2
CONTENT_MODE = "content"
FILES_MODE = "files_with_matches"
COUNT_MODE = "count"


@dataclass
class GrepHit:
    """A single parsed line from a Grep content-mode response."""

    file_path: Path
    line: int
    text: str


@dataclass
class AnnotateRequest:
    """Request to annotate a single GrepHit against a RepoMap."""

    repo_map: RepoMap
    hit: GrepHit


def _parse_event(raw: dict) -> Tuple[Path, dict]:
    """Extract project_root and tool_response from the hook event dict."""
    project_root = Path(raw.get("cwd") or raw.get("project_root", ""))
    tool_response = raw.get("tool_response", {})
    return project_root, tool_response


def _parse_content_hits(content: str) -> List[GrepHit]:
    """Parse newline-separated content lines into a list of GrepHit objects."""
    hits: List[GrepHit] = []
    for raw_line in content.split("\n"):
        if not raw_line:
            continue
        parts = raw_line.split(":", SPLIT_MAX_COLONS)
        if len(parts) < SPLIT_MAX_COLONS + 1:
            logger.warning("Skipping malformed grep hit: %r", raw_line)
            continue
        try:
            line_num = int(parts[1])
        except ValueError:
            logger.debug("skipping malformed grep hit: %s", raw_line)
            continue
        hits.append(GrepHit(Path(parts[0]), line_num, parts[SPLIT_MAX_COLONS]))
    return hits


def _find_enclosing_symbol(file_index: FileIndex, line: int) -> Optional[str]:
    """Return annotation string for the symbol enclosing line, or None."""
    for symbol in file_index.symbols:
        if symbol.line <= line <= symbol.end_line:
            return f"[in {symbol.name}(), lines {symbol.line}-{symbol.end_line}]"
    return None


def _annotate_hit(request: AnnotateRequest) -> str:
    """Return annotation string for a single GrepHit using the repo map."""
    hit = request.hit
    store_req = StoreRequest(
        repo_map=request.repo_map,
        file_path=str(hit.file_path),
    )
    file_index = get_or_index(store_req)
    enclosing = _find_enclosing_symbol(file_index, hit.line)
    label = enclosing if enclosing is not None else MODULE_LEVEL_LABEL
    return f"{hit.file_path}:{hit.line} {label}"


def _build_response(additional_context: str) -> str:
    """Serialize the hook response JSON with additionalContext."""
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": additional_context,
        }
    })


def _collect_annotations(hits: List[GrepHit], project_root: Path) -> str:
    """Load map, annotate all hits, persist, and return joined annotation block."""
    repo_map = load_map(project_root)
    annotations: List[str] = []
    for hit in hits:
        try:
            annotations.append(_annotate_hit(AnnotateRequest(repo_map, hit)))
        except Exception:
            logger.exception("Failed to annotate hit %s:%s", hit.file_path, hit.line)
    save_map(repo_map)
    return "\n".join(annotations)


def main() -> None:
    """Entry point: parse stdin, annotate hits, write response to stdout."""
    try:
        raw = json.loads(sys.stdin.read())
    except Exception:
        logger.exception("Failed to parse stdin JSON")
        sys.exit(0)

    try:
        project_root, tool_response = _parse_event(raw)
    except Exception:
        logger.exception("Failed to parse hook event")
        sys.exit(0)

    mode = tool_response.get("mode", "")

    if mode != CONTENT_MODE:
        logger.info("Skipping enrichment for mode=%r", mode)
        return

    content = tool_response.get("content", "")
    hits = _parse_content_hits(content)

    if not hits:
        logger.info("No hits to annotate")
        return

    block = _collect_annotations(hits, project_root)
    sys.stdout.write(_build_response(block))


if __name__ == "__main__":
    main()
