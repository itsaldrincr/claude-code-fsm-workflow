import json
from pathlib import Path

from src import config
from src.fsm_core.claude_session_backend import (
    dispatch_workers_parallel,
    enqueue_advisor_intent,
    enqueue_worker_intents,
    mark_result_applied,
    read_pending_intents,
    read_pending_results,
    write_result_for_intent,
)
from src.fsm_core.dispatch_contract import AdvisorDispatchRequest, WorkerDispatchRequest


class TestIntentEnqueue:
    def test_enqueue_worker_intents_creates_files(self, tmp_path: Path) -> None:
        req = WorkerDispatchRequest(task_path=str(tmp_path / "task_001.md"), dispatch_role="fsm-executor")
        intents = enqueue_worker_intents(tmp_path, [req])
        assert len(intents) == 1
        intent_file = tmp_path / config.CLAUDE_SESSION_INTENTS_DIR / f"{intents[0].intent_id}.json"
        assert intent_file.exists()

    def test_enqueue_advisor_intent_creates_file(self, tmp_path: Path) -> None:
        req = AdvisorDispatchRequest(task_paths=[str(tmp_path / "task_001.md")])
        intent = enqueue_advisor_intent(tmp_path, req)
        intent_file = tmp_path / config.CLAUDE_SESSION_INTENTS_DIR / f"{intent.intent_id}.json"
        assert intent_file.exists()


class TestPendingIntentsAndResults:
    def test_pending_intents_list_excludes_completed(self, tmp_path: Path) -> None:
        req = WorkerDispatchRequest(task_path=str(tmp_path / "task_001.md"), dispatch_role="fsm-executor")
        intent = enqueue_worker_intents(tmp_path, [req])[0]
        pending = read_pending_intents(tmp_path)
        assert len(pending) == 1
        write_result_for_intent(tmp_path, intent.intent_id, 0, "ok", "")
        pending_after = read_pending_intents(tmp_path)
        assert pending_after == []

    def test_write_result_and_read_pending_results(self, tmp_path: Path) -> None:
        req = WorkerDispatchRequest(task_path=str(tmp_path / "task_001.md"), dispatch_role="fsm-executor")
        intent = enqueue_worker_intents(tmp_path, [req])[0]
        result_path = write_result_for_intent(tmp_path, intent.intent_id, 0, "stdout", "stderr")
        assert result_path.exists()
        pending_results = read_pending_results(tmp_path)
        assert len(pending_results) == 1
        assert pending_results[0].intent_id == intent.intent_id
        assert pending_results[0].exit_code == 0
        assert pending_results[0].stdout == "stdout"

    def test_mark_result_applied_moves_file(self, tmp_path: Path) -> None:
        req = WorkerDispatchRequest(task_path=str(tmp_path / "task_001.md"), dispatch_role="fsm-executor")
        intent = enqueue_worker_intents(tmp_path, [req])[0]
        result_path = write_result_for_intent(tmp_path, intent.intent_id, 0, "ok", "")
        moved = mark_result_applied(tmp_path, result_path)
        assert moved.exists()
        assert not result_path.exists()
        assert moved.parent.name == "applied"


class TestDispatchCompatibilityWrapper:
    def test_dispatch_workers_parallel_returns_queued_result(self, tmp_path: Path) -> None:
        req = WorkerDispatchRequest(task_path=str(tmp_path / "task_001.md"), dispatch_role="fsm-executor")
        results = dispatch_workers_parallel(workspace=tmp_path, requests=[req])
        assert len(results) == 1
        assert results[0].exit_code == 125
        assert results[0].stderr == "queued"
