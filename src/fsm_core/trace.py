"""JSONL event trace — TraceEvent schema + append_event + main entry point."""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG_BASE_DIR_ENV: str = "CLAUDE_HOOKS_LOG_DIR"
CLAUDE_DIR_NAME: str = ".claude"
TRACE_DIR_NAME: str = "fsm-trace"
LOG_BASE_DIR_DEFAULT: Path = Path.home() / CLAUDE_DIR_NAME / TRACE_DIR_NAME

TOOL_INPUT_SUMMARY_LIMIT: int = 200
TOOL_RESULT_STATUS_OK: str = "ok"
TOOL_RESULT_STATUS_ERROR: str = "error"
TOOL_RESULT_STATUS_BLOCKED: str = "blocked"
TOOL_RESULT_STATUS_UNKNOWN: str = "unknown"
HOOK_DECISION_NA: str = "n/a"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceEvent:
    """One trace entry written to a JSONL file."""

    session_id: str
    timestamp: str
    event_type: str
    agent_type: str | None
    tool_name: str
    tool_input_summary: str
    tool_result_status: str
    hook_decision: str
    decision_reason: str


@dataclass(frozen=True)
class AppendRequest:
    """Arguments for append_event — keeps the function to 1 param."""

    event: TraceEvent
    base_dir: Path


def resolve_base_dir() -> Path:
    """Return LOG_BASE_DIR_DEFAULT or env override."""
    override = os.environ.get(LOG_BASE_DIR_ENV)
    if override:
        return Path(override)
    return LOG_BASE_DIR_DEFAULT


def _derive_tool_result_status(tool_response: object) -> str:
    """Map tool_response value to one of ok/error/blocked/unknown."""
    if tool_response is None:
        return TOOL_RESULT_STATUS_UNKNOWN
    if not isinstance(tool_response, dict):
        return TOOL_RESULT_STATUS_OK
    if tool_response.get("type") == "error" or "error" in tool_response:
        return TOOL_RESULT_STATUS_ERROR
    if tool_response.get("decision") == "block":
        return TOOL_RESULT_STATUS_BLOCKED
    return TOOL_RESULT_STATUS_OK


def _extract_hook_decision(data: dict) -> tuple[str, str]:
    """Return (hook_decision, decision_reason) from hook response field."""
    hook_response = data.get("hook_response") or {}
    decision = hook_response.get("decision", HOOK_DECISION_NA) if isinstance(hook_response, dict) else HOOK_DECISION_NA
    reason = hook_response.get("reason", "") if isinstance(hook_response, dict) else ""
    return decision, reason


def build_event_from_stdin(raw_json: str) -> TraceEvent:
    """Parse a hook event JSON from stdin, extract fields, return TraceEvent."""
    data: dict = json.loads(raw_json)
    input_data: dict = data if isinstance(data, dict) else {}
    tool_input = input_data.get("tool_input") or {}
    tool_input_summary = json.dumps(tool_input)[:TOOL_INPUT_SUMMARY_LIMIT]
    tool_response = input_data.get("tool_response")
    hook_decision, decision_reason = _extract_hook_decision(input_data)
    return TraceEvent(
        session_id=input_data.get("session_id", ""),
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=input_data.get("hook_event_name", ""),
        agent_type=input_data.get("agent_type") or None,
        tool_name=input_data.get("tool_name") or "",
        tool_input_summary=tool_input_summary,
        tool_result_status=_derive_tool_result_status(tool_response),
        hook_decision=hook_decision,
        decision_reason=decision_reason,
    )


def append_event(request: AppendRequest) -> None:
    """Append one JSONL line to <base_dir>/<session_id>/<event_type>.jsonl.

    On OSError: logs to stderr and returns normally. Never raises.
    """
    event = request.event
    log_dir = request.base_dir / event.session_id
    log_dir.mkdir(parents=True, exist_ok=True)
    event_type_safe = event.event_type or "unknown"
    target = log_dir / f"{event_type_safe}.jsonl"
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event)) + "\n")
    except OSError as exc:
        msg = f"append_event OSError: {exc}\n"
        logging.getLogger(__name__).error("append_event OSError: %s", exc, exc_info=False)
        sys.stderr.write(msg)


def main() -> int:
    """Entry point called by hooks/post_tool_trace.sh. Always returns 0."""
    try:
        raw = sys.stdin.read()
        event = build_event_from_stdin(raw)
        base_dir = resolve_base_dir()
        append_event(AppendRequest(event=event, base_dir=base_dir))
    except Exception as exc:
        logger.error("trace main error: %s", exc, exc_info=True)
        sys.stderr.write(f"trace main error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
