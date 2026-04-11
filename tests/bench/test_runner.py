"""Integration tests for bench/runner.py."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bench.runner import RunnerRequest, run_batch


def _make_workspace(parent: Path, name: str) -> Path:
    ws = parent / name
    ws.mkdir()
    return ws


def _make_manifest(parent: Path, instances: list[dict]) -> Path:
    p = parent / "manifest.json"
    p.write_text(json.dumps(instances))
    return p


@pytest.fixture
def orchestrate_script(tmp_path: Path) -> Path:
    script = tmp_path / "orchestrate.py"
    script.write_text("# dummy\n")
    return script


def test_run_batch_two_instance_success(tmp_path: Path, orchestrate_script: Path) -> None:
    """AC2.3: 2-instance list with mocked exit-0 produces two bench_result.json + aggregate."""
    ws1 = _make_workspace(tmp_path, "ws1")
    ws2 = _make_workspace(tmp_path, "ws2")
    manifest = _make_manifest(tmp_path, [
        {"instance_id": "i1", "workspace_path": str(ws1), "expected_patch": "diff\n"},
        {"instance_id": "i2", "workspace_path": str(ws2), "expected_patch": "diff\n"},
    ])
    request = RunnerRequest(
        manifest_path=manifest,
        baselines_dir=tmp_path / "baselines",
        orchestrate_script=orchestrate_script,
        timeout_seconds=60,
    )

    with (
        patch("bench.run_one._run_orchestrate_once", side_effect=[0, 0]),
        patch("bench.run_one._capture_patch", return_value="diff\n"),
        patch("bench.run_one._evaluate_patch", return_value=1.0),
        patch("bench.run_one._query_final_states", return_value=[]),
    ):
        summary = run_batch(request)

    assert summary.pass_count == 2
    assert summary.fail_count == 0
    assert summary.retry_exhausted_count == 0
    assert (ws1 / "bench_result.json").exists()
    assert (ws2 / "bench_result.json").exists()
    assert summary.aggregate_path.exists()
    data = json.loads(summary.aggregate_path.read_text())
    assert data["instance_count"] == 2
    statuses = {r["instance_id"]: r["status"] for r in data["results"]}
    assert statuses["i1"] == "pass"
    assert statuses["i2"] == "pass"


def test_run_batch_retry_exhausted_continues(tmp_path: Path, orchestrate_script: Path) -> None:
    """AC2.4: instance exhausting retries records retry_exhausted; batch continues."""
    ws1 = _make_workspace(tmp_path, "ws1")
    ws2 = _make_workspace(tmp_path, "ws2")
    manifest = _make_manifest(tmp_path, [
        {"instance_id": "retry_inst", "workspace_path": str(ws1), "expected_patch": ""},
        {"instance_id": "pass_inst", "workspace_path": str(ws2), "expected_patch": "diff\n"},
    ])
    request = RunnerRequest(
        manifest_path=manifest,
        baselines_dir=tmp_path / "baselines",
        orchestrate_script=orchestrate_script,
        timeout_seconds=60,
    )

    # retry_inst: exit 4 twice (retry_once policy exhausted); pass_inst: exit 0
    with (
        patch("bench.run_one._run_orchestrate_once", side_effect=[4, 4, 0]),
        patch("bench.run_one._capture_patch", return_value="diff\n"),
        patch("bench.run_one._evaluate_patch", return_value=1.0),
        patch("bench.run_one._query_final_states", return_value=[]),
    ):
        summary = run_batch(request)

    assert summary.retry_exhausted_count == 1
    assert summary.pass_count == 1
    assert summary.fail_count == 0
    assert summary.aggregate_path.exists()
    data = json.loads(summary.aggregate_path.read_text())
    assert data["instance_count"] == 2
    statuses = {r["instance_id"]: r["status"] for r in data["results"]}
    assert statuses["retry_inst"] == "retry_exhausted"
    assert statuses["pass_inst"] == "pass"
