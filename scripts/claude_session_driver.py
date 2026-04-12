"""Helper CLI for Claude-session intent/result workflow."""

import argparse
import json
import logging
import sys
from pathlib import Path

from src.fsm_core.claude_session_backend import read_pending_intents, write_result_for_intent

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="claude_session intent/result helper")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--list-pending", action="store_true", help="Print pending intents as JSON and exit")
    parser.add_argument("--write-result", action="store_true", help="Write a result envelope for an intent")
    parser.add_argument("--intent-id", default="", help="Intent ID to write result for")
    parser.add_argument("--exit-code", type=int, default=0, help="Result exit code")
    parser.add_argument("--stdout", default="", help="Result stdout payload")
    parser.add_argument("--stderr", default="", help="Result stderr payload")
    return parser.parse_args()


def _emit(payload: dict[str, object]) -> None:
    """Print one JSON object to stdout."""
    sys.stdout.write(json.dumps(payload) + "\n")


def main() -> int:
    """List pending intents or write one result envelope."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    workspace = Path(args.workspace)
    try:
        if args.list_pending or not args.write_result:
            pending = read_pending_intents(workspace)
            _emit({"action": "list_pending", "count": len(pending), "intents": pending})
            return 0
        if not args.intent_id:
            _emit({"action": "write_result", "error": "--intent-id is required"})
            return 2
        path = write_result_for_intent(
            workspace=workspace,
            intent_id=args.intent_id,
            exit_code=args.exit_code,
            stdout=args.stdout,
            stderr=args.stderr,
        )
        _emit({"action": "write_result", "intent_id": args.intent_id, "result_path": str(path)})
        return 0
    except Exception as exc:
        logger.error("claude_session driver failed: %s", exc)
        _emit({"action": "claude_session_driver", "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())

