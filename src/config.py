"""Central configuration constants for the FSM pipeline orchestrator."""

from typing import Final, Literal

DispatchMode = Literal["claude_session"]

DISPATCH_MODE: DispatchMode = "claude_session"
MODEL_MAP: dict[str, str] = {"fsm-executor": "haiku", "fsm-integrator": "sonnet", "bug-scanner": "sonnet"}
DEFAULT_WORKER_MODEL: str = "haiku"
ADVISOR_MODEL: str = "opus"
BUG_SCANNER_MODEL: str = "sonnet"
IS_BUG_SCANNER_PAIR_ENABLED: Final[bool] = True
NUM_BUG_SCANNERS: int = 2
MAX_PARALLEL_WORKERS: int = 30
DAEMON_POLL_INTERVAL_SECONDS: float = 2.0
GRACEFUL_SHUTDOWN_SECONDS: float = 5.0
ORCHESTRATE_LOCK_PATH: str = ".orchestrate.lock"
WORKER_HEARTBEAT_DIR: str = ".fsm-worker-hb"
WORKER_HEARTBEAT_STALE_SECONDS: int = 120
IS_ADVISOR_CACHE_ENABLED: Final[bool] = True
ADVISOR_CACHE_DIR: str = ".fsm-advisor-cache"
IS_DETERMINISTIC_GATE_ENABLED: Final[bool] = True
EXIT_TURN_LIMIT: int = 125
CLAUDE_SESSION_INTENTS_DIR: str = ".fsm-intents"
CLAUDE_SESSION_RESULTS_DIR: str = ".fsm-results"
CLAUDE_SESSION_DRIVER_SCRIPT: str = "scripts/claude_session_driver.py"
CLAUDE_SESSION_DRIVER_TIMEOUT_SECONDS: int = 1800
