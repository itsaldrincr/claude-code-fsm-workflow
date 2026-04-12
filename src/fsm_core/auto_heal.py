"""Stale task detection for auto-heal workflow (no MAP.md writes — 817b handles that)."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config import WORKER_HEARTBEAT_STALE_SECONDS
from src.fsm_core.map_reader import ReadTasksRequest, read_task_dispatch_info
from src.fsm_core.map_io import StatusUpdateRequest, update_map_status
from src.fsm_core.trace import TraceEvent, AppendRequest, append_event, resolve_base_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealResult:
    """Result of a single stale-task scan."""

    task_id: str
    last_hb_iso: str
    reason: str


def _read_heartbeat(hb_path: Path) -> str | None:
    """Read last_hb_iso from heartbeat JSON, or return None if missing/invalid."""
    try:
        data = json.loads(hb_path.read_text(encoding="utf-8"))
        return data.get("last_hb_iso")
    except Exception as exc:
        logger.warning("Failed to read heartbeat %s: %s", hb_path, exc)
        return None


def _is_stale(last_hb_iso: str) -> bool:
    """Check if heartbeat is older than WORKER_HEARTBEAT_STALE_SECONDS."""
    try:
        normalized = last_hb_iso.replace("Z", "+00:00")
        last_hb = datetime.fromisoformat(normalized)
        if last_hb.tzinfo is None:
            last_hb = last_hb.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - last_hb).total_seconds()
        return age_seconds > WORKER_HEARTBEAT_STALE_SECONDS
    except Exception as exc:
        logger.warning("Malformed heartbeat timestamp %r: %s", last_hb_iso, exc)
        return True


def _check_one_task(task: object, hb_dir: Path) -> HealResult | None:
    """Check heartbeat for a single task. Return HealResult if stale/missing, else None."""
    hb_path = hb_dir / f"{task.task_id}.json"
    if not hb_path.exists():
        return HealResult(task.task_id, "", "missing heartbeat")

    last_hb_iso = _read_heartbeat(hb_path)
    if not last_hb_iso:
        return HealResult(task.task_id, "", "invalid heartbeat")

    if _is_stale(last_hb_iso):
        return HealResult(task.task_id, last_hb_iso, "stale heartbeat")

    return None


def _scan_stale(workspace: Path) -> list[HealResult]:
    """Scan workspace for stale IN_PROGRESS tasks.

    For each IN_PROGRESS task, check its heartbeat file. Return HealResult entries
    for tasks with missing or stale heartbeats (older than WORKER_HEARTBEAT_STALE_SECONDS).
    """
    map_path = workspace / "MAP.md"
    request = ReadTasksRequest(workspace=workspace, map_path=map_path)
    tasks = read_task_dispatch_info(request)

    hb_dir = workspace / ".fsm-worker-hb"
    results: list[HealResult] = []

    for task in tasks:
        if task.status != "IN_PROGRESS":
            continue
        result = _check_one_task(task, hb_dir)
        if result:
            results.append(result)

    return results


def _flip_one_task(task_id: str, map_path: Path) -> None:
    """Flip one task's status from IN_PROGRESS → PENDING under map_lock."""
    req = StatusUpdateRequest(map_path=map_path, task_id=task_id, new_status="PENDING")
    update_map_status(req)


@dataclass(frozen=True, slots=True)
class _HealEventParams:
    """Bundled params for _emit_heal_event — keeps function to 1 arg."""

    task_id: str
    reason: str
    last_hb_iso: str


def _emit_heal_event(params: _HealEventParams) -> None:
    """Emit trace event for healed task (orchestrator-tier event, not SDK)."""
    summary = f"task_id={params.task_id}, reason={params.reason}, last_hb_iso={params.last_hb_iso}"
    event = TraceEvent(
        session_id="",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type="auto_heal_stale",
        agent_type=None,
        tool_name="auto_heal",
        tool_input_summary=summary,
        tool_result_status="ok",
        hook_decision="n/a",
        decision_reason="",
    )
    base_dir = resolve_base_dir()
    append_event(AppendRequest(event=event, base_dir=base_dir))


def heal_stale_in_progress(workspace: Path) -> list[str]:
    """Heal stale IN_PROGRESS tasks by flipping to PENDING.

    Scans for tasks with missing/invalid/stale heartbeats, flips each via
    update_map_status under map_lock, emits trace event per task.
    Returns list of healed task IDs.
    """
    results = _scan_stale(workspace)
    map_path = workspace / "MAP.md"
    healed_ids: list[str] = []

    for result in results:
        _flip_one_task(result.task_id, map_path)
        _emit_heal_event(_HealEventParams(task_id=result.task_id, reason=result.reason, last_hb_iso=result.last_hb_iso))
        healed_ids.append(result.task_id)

    return healed_ids
