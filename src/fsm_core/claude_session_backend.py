"""Intent/result envelope backend for Claude-session-native dispatch."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from src import config
from src.fsm_core.dispatch_contract import (
    AdvisorDispatchRequest,
    DispatchResult,
    ReviseDispatchRequest,
    WorkerDispatchRequest,
)

INTENT_SCHEMA_VERSION = "1"
RESULT_SCHEMA_VERSION = "1"
SUMMARY_LIMIT = 2000
APPLIED_RESULTS_DIR = "applied"
QUEUED_EXIT_CODE = 125


@dataclass(frozen=True)
class WorkerIntentEnvelope:
    """Serialized dispatch intent for one worker task."""

    schema_version: str
    intent_id: str
    kind: str
    task_path: str
    dispatch_role: str
    created_at: str


@dataclass(frozen=True)
class AdvisorScannerConfig:
    """Configuration for advisor scanner pair assignment."""

    pair_key: str = ""
    scanner_index: int = 0
    scanner_total: int = 1


@dataclass(frozen=True)
class AdvisorIntentEnvelope:
    """Serialized dispatch intent for one wave-gate review run."""

    schema_version: str
    intent_id: str
    kind: str
    task_paths: tuple[str, ...]
    created_at: str
    pair_key: str = ""
    scanner_index: int = 0
    scanner_total: int = 1


@dataclass(frozen=True)
class ResultPayload:
    """Parameters for writing a result envelope."""

    intent_id: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PendingResult:
    """Pending result envelope loaded from .fsm-results."""

    result_path: Path
    intent_id: str
    kind: str
    exit_code: int
    stdout: str
    stderr: str
    task_path: str = ""
    dispatch_role: str = ""
    task_paths: tuple[str, ...] = ()
    pair_key: str = ""
    scanner_index: int = 0
    scanner_total: int = 1


def _utc_now() -> str:
    """Return UTC timestamp in RFC3339 format."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs(workspace: Path) -> tuple[Path, Path, Path]:
    """Create and return intents/results/applied directories under workspace."""
    intents_dir = workspace / config.CLAUDE_SESSION_INTENTS_DIR
    results_dir = workspace / config.CLAUDE_SESSION_RESULTS_DIR
    applied_dir = results_dir / APPLIED_RESULTS_DIR
    intents_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    applied_dir.mkdir(parents=True, exist_ok=True)
    return intents_dir, results_dir, applied_dir


def _intent_path(intents_dir: Path, intent_id: str) -> Path:
    """Return filesystem path for an intent envelope."""
    return intents_dir / f"{intent_id}.json"


def _result_path(results_dir: Path, intent_id: str) -> Path:
    """Return filesystem path for a result envelope."""
    return results_dir / f"{intent_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON payload with deterministic formatting."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary(text: str) -> str:
    """Truncate text for compact summaries in result envelopes."""
    cleaned = text.strip()
    if len(cleaned) <= SUMMARY_LIMIT:
        return cleaned
    return cleaned[:SUMMARY_LIMIT]


def enqueue_worker_intents(workspace: Path, requests: list[WorkerDispatchRequest]) -> list[WorkerIntentEnvelope]:
    """Persist worker intents and return envelopes in request order."""
    intents_dir, _, _ = _ensure_dirs(workspace)
    intents: list[WorkerIntentEnvelope] = []
    for req in requests:
        envelope = WorkerIntentEnvelope(
            schema_version=INTENT_SCHEMA_VERSION,
            intent_id=f"intent_{uuid.uuid4().hex}",
            kind="worker",
            task_path=str(Path(req.task_path).resolve()),
            dispatch_role=req.dispatch_role,
            created_at=_utc_now(),
        )
        _write_json(_intent_path(intents_dir, envelope.intent_id), asdict(envelope))
        intents.append(envelope)
    return intents


@dataclass(frozen=True)
class AdvisorIntentRequest:
    """Bundled request for persisting one advisor review intent."""

    request: AdvisorDispatchRequest
    scanner_config: AdvisorScannerConfig = AdvisorScannerConfig()


def enqueue_advisor_intent(workspace: Path, intent_req: AdvisorIntentRequest) -> AdvisorIntentEnvelope:
    """Persist one review intent."""
    intents_dir, _, _ = _ensure_dirs(workspace)
    envelope = AdvisorIntentEnvelope(
        schema_version=INTENT_SCHEMA_VERSION,
        intent_id=f"intent_{uuid.uuid4().hex}",
        kind="advisor",
        task_paths=tuple(str(Path(p).resolve()) for p in intent_req.request.task_paths),
        pair_key=intent_req.scanner_config.pair_key,
        scanner_index=intent_req.scanner_config.scanner_index,
        scanner_total=intent_req.scanner_config.scanner_total,
        created_at=_utc_now(),
    )
    _write_json(_intent_path(intents_dir, envelope.intent_id), asdict(envelope))
    return envelope


def enqueue_revise_intent(workspace: Path, request: ReviseDispatchRequest) -> WorkerIntentEnvelope:
    """Persist one revise intent as a worker-kind intent."""
    intents_dir, _, _ = _ensure_dirs(workspace)
    envelope = WorkerIntentEnvelope(
        schema_version=INTENT_SCHEMA_VERSION,
        intent_id=f"intent_{uuid.uuid4().hex}",
        kind="revise",
        task_path=str(Path(request.task_path).resolve()),
        dispatch_role=request.dispatch_role,
        created_at=_utc_now(),
    )
    payload = asdict(envelope)
    payload["guidance"] = request.guidance
    _write_json(_intent_path(intents_dir, envelope.intent_id), payload)
    return envelope


def read_pending_intents(workspace: Path) -> list[dict[str, Any]]:
    """Return pending intents without corresponding result envelopes."""
    intents_dir, results_dir, _ = _ensure_dirs(workspace)
    pending: list[dict[str, Any]] = []
    for path in sorted(intents_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        intent_id = str(data.get("intent_id", ""))
        if not intent_id:
            continue
        if _result_path(results_dir, intent_id).exists():
            continue
        pending.append(data)
    return pending


def _base_result_fields(payload_params: ResultPayload) -> dict[str, Any]:
    """Build the common fields for a result envelope."""
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "intent_id": payload_params.intent_id,
        "exit_code": int(payload_params.exit_code),
        "stdout_summary": _summary(payload_params.stdout),
        "stderr_summary": _summary(payload_params.stderr),
        "stdout": payload_params.stdout,
        "stderr": payload_params.stderr,
        "created_at": _utc_now(),
        "completed_at": _utc_now(),
    }


def _build_result_payload(intent: dict[str, Any], payload_params: ResultPayload) -> dict[str, Any]:
    """Build result payload dict from intent and parameters."""
    kind = str(intent.get("kind", ""))
    payload = {**_base_result_fields(payload_params), "kind": kind}
    if kind in ("worker", "revise"):
        payload["task_path"] = str(intent.get("task_path", ""))
        payload["dispatch_role"] = str(intent.get("dispatch_role", ""))
    if kind == "advisor":
        payload["task_paths"] = list(intent.get("task_paths", []))
        payload["pair_key"] = str(intent.get("pair_key", ""))
        payload["scanner_index"] = int(intent.get("scanner_index", 0))
        payload["scanner_total"] = int(intent.get("scanner_total", 1))
    return payload


def write_result_for_intent(
    workspace: Path,
    payload: ResultPayload,
) -> Path:
    """Write a result envelope for an existing intent and return result path."""
    intents_dir, results_dir, _ = _ensure_dirs(workspace)
    intent_path = _intent_path(intents_dir, payload.intent_id)
    if not intent_path.exists():
        raise FileNotFoundError(f"Intent not found: {payload.intent_id}")
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    result_payload = _build_result_payload(intent, payload)
    path = _result_path(results_dir, payload.intent_id)
    _write_json(path, result_payload)
    return path


def _parse_pending_result(path: Path, data: dict[str, Any]) -> PendingResult:
    """Parse one result file into a PendingResult."""
    return PendingResult(
        result_path=path,
        intent_id=str(data.get("intent_id", "")),
        kind=str(data.get("kind", "")),
        exit_code=int(data.get("exit_code", 1)),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        task_path=str(data.get("task_path", "")),
        dispatch_role=str(data.get("dispatch_role", "")),
        task_paths=tuple(str(p) for p in data.get("task_paths", [])),
        pair_key=str(data.get("pair_key", "")),
        scanner_index=int(data.get("scanner_index", 0)),
        scanner_total=int(data.get("scanner_total", 1)),
    )


def read_pending_results(workspace: Path) -> list[PendingResult]:
    """Load unapplied result envelopes from .fsm-results."""
    _, results_dir, _ = _ensure_dirs(workspace)
    pending: list[PendingResult] = []
    for path in sorted(results_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        pending.append(_parse_pending_result(path, data))
    return pending


def mark_result_applied(workspace: Path, result_path: Path) -> Path:
    """Move one result envelope into applied/ to make processing idempotent."""
    _, _, applied_dir = _ensure_dirs(workspace)
    target = applied_dir / result_path.name
    result_path.rename(target)
    return target


def dispatch_workers_parallel(workspace: Path, requests: list[WorkerDispatchRequest]) -> list[DispatchResult]:
    """Compatibility wrapper: enqueue worker intents and return queued statuses."""
    intents = enqueue_worker_intents(workspace, requests)
    return [DispatchResult(exit_code=QUEUED_EXIT_CODE, stdout=i.intent_id, stderr="queued") for i in intents]


def dispatch_advisor(workspace: Path, request: AdvisorDispatchRequest) -> DispatchResult:
    """Compatibility wrapper: enqueue advisor intent and return queued status."""
    intent = enqueue_advisor_intent(workspace, AdvisorIntentRequest(request=request))
    return DispatchResult(exit_code=QUEUED_EXIT_CODE, stdout=intent.intent_id, stderr="queued")


def dispatch_revise(workspace: Path, request: ReviseDispatchRequest) -> DispatchResult:
    """Compatibility wrapper: enqueue revise intent and return queued status."""
    intent = enqueue_revise_intent(workspace, request)
    return DispatchResult(exit_code=QUEUED_EXIT_CODE, stdout=intent.intent_id, stderr="queued")
