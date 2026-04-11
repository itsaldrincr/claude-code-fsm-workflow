"""Batch entry point for SWE-bench instance evaluation."""

import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bench.config import BENCH_INSTANCE_TIMEOUT_SECONDS, BENCH_RETRY_POLICY
from bench.run_one import RunOneRequest, RunOneResult, run_one

logger = logging.getLogger(__name__)


@dataclass
class RunnerRequest:
    """Parameters for a batch benchmark run."""

    manifest_path: Path
    baselines_dir: Path
    orchestrate_script: Path
    timeout_seconds: int = BENCH_INSTANCE_TIMEOUT_SECONDS


@dataclass
class RunnerSummary:
    """Aggregate results for a completed batch run."""

    results: list[RunOneResult]
    aggregate_path: Path
    pass_count: int
    fail_count: int
    retry_exhausted_count: int


def run_batch(request: RunnerRequest) -> RunnerSummary:
    """Run all instances in the manifest and aggregate results."""
    instances = _iterate_instances(request)
    results: list[RunOneResult] = []
    for instance_req in instances:
        result = run_one(instance_req)
        results.append(result)
        logger.info("Instance %s completed: %s", result.instance_id, _classify_status(result))
    aggregate_path = _aggregate_results(results, request.baselines_dir)
    return _build_summary(results, aggregate_path)


def _iterate_instances(request: RunnerRequest) -> list[RunOneRequest]:
    """Load manifest JSON and return a RunOneRequest per instance."""
    raw: list[dict] = json.loads(request.manifest_path.read_text())
    return [
        RunOneRequest(
            workspace_path=Path(entry["workspace_path"]),
            instance_id=entry["instance_id"],
            expected_patch=entry.get("expected_patch", ""),
            orchestrate_script=request.orchestrate_script,
            timeout_seconds=request.timeout_seconds,
            result_dir=Path(entry["result_dir"]) if "result_dir" in entry else None,
        )
        for entry in raw
    ]


def _aggregate_results(results: list[RunOneResult], baselines_dir: Path) -> Path:
    """Write aggregate JSON atomically to baselines_dir/run_<timestamp>.json."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = baselines_dir / f"run_{timestamp}.json"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    data = _build_aggregate_data(results, timestamp)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=baselines_dir, suffix=".tmp", delete=False
    ) as fh:
        json.dump(data, fh, indent=2)
        tmp_path = Path(fh.name)
    tmp_path.replace(target)
    logger.info("Wrote aggregate to %s", target)
    return target


def _build_aggregate_data(results: list[RunOneResult], timestamp: str) -> dict:
    """Build the aggregate JSON payload from per-instance results."""
    return {
        "timestamp": timestamp,
        "instance_count": len(results),
        "results": [
            {
                "instance_id": r.instance_id,
                "status": _classify_status(r),
                "exit_code": r.exit_code,
                "eval_score": r.eval_score,
                "bench_result_path": str(r.bench_result_path),
            }
            for r in results
        ],
    }


def _classify_status(result: RunOneResult) -> str:
    """Return retry_exhausted if retries were drained, else the raw status."""
    policy = BENCH_RETRY_POLICY.get(result.exit_code, "fail")
    if policy == "retry_once" and result.status == "fail":
        return "retry_exhausted"
    return result.status


def _build_summary(results: list[RunOneResult], aggregate_path: Path) -> RunnerSummary:
    """Build RunnerSummary from completed results and aggregate path."""
    statuses = [_classify_status(r) for r in results]
    return RunnerSummary(
        results=results,
        aggregate_path=aggregate_path,
        pass_count=statuses.count("pass"),
        fail_count=statuses.count("fail"),
        retry_exhausted_count=statuses.count("retry_exhausted"),
    )
