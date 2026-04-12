import dataclasses
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path

from src.config import WORKER_HEARTBEAT_DIR


@dataclass(frozen=True, slots=True)
class HeartbeatPayload:
    task_id: str
    last_hb_iso: str
    tool_count: int
    dispatch_mode: str


@dataclass(frozen=True, slots=True)
class WriteHeartbeatRequest:
    task_id: str
    workspace: Path
    tool_count: int
    dispatch_mode: str


def write_heartbeat(request: WriteHeartbeatRequest) -> None:
    """Write task heartbeat atomically to workspace/.fsm-worker-hb directory."""
    hb_dir = request.workspace / WORKER_HEARTBEAT_DIR
    hb_dir.mkdir(parents=True, exist_ok=True)

    payload = HeartbeatPayload(
        task_id=request.task_id,
        last_hb_iso=datetime.now(timezone.utc).isoformat(),
        tool_count=request.tool_count,
        dispatch_mode=request.dispatch_mode,
    )

    final_path = hb_dir / f"{request.task_id}.json"

    with tempfile.NamedTemporaryFile(
        mode="w", dir=hb_dir, delete=False, suffix=".tmp"
    ) as tmp_file:
        tmp_path = tmp_file.name
        json.dump(dataclasses.asdict(payload), tmp_file)

    os.replace(tmp_path, final_path)
