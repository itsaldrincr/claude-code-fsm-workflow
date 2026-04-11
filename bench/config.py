"""Benchmark configuration constants.

This module defines all tuneable parameters for SWE-bench instance evaluation.
Stdlib only; constants only.
"""

# Instance execution timeout in seconds (30 minutes).
BENCH_INSTANCE_TIMEOUT_SECONDS: int = 1800

# Evaluation backend: "local" (default, fast heuristic) or "official" (requires swebench).
BENCH_EVAL_BACKEND: str = "local"

# Default workspace root for isolated benchmark instances.
BENCH_DEFAULT_WORKSPACE_ROOT: str = "/tmp/fsm-bench"

# Retry policy: maps orchestrate.py exit code → policy string.
# 0 = orchestrate succeeded, instance passed
# 3 = orchestrate unrecoverable failure, instance failed
# 4 = orchestrate transient failure, retry once
# 5 = orchestrate context overflow, instance failed
BENCH_RETRY_POLICY: dict[int, str] = {
    0: "pass",
    3: "fail",
    4: "retry_once",
    5: "fail",
}
