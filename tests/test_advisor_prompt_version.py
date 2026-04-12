"""Test that bug-scanner system prompt hash matches pinned version.

This test enforces a contract: the bug-scanner system prompt body
is versioned via SHA256 hash, and every edit to the prompt must be
accompanied by a bump to both EXPECTED_BUG_SCANNER_PROMPT_SHA256
(below) and ADVISOR_PROMPT_VERSION in src/fsm_core/advisor_cache.py.

Manual bump procedure:
  1. Edit ~/.claude/agents/bug-scanner.md (the prompt body, not metadata).
  2. Run this test — it will fail with the new hash.
  3. Copy the new hash into EXPECTED_BUG_SCANNER_PROMPT_SHA256 below.
  4. Increment ADVISOR_PROMPT_VERSION in src/fsm_core/advisor_cache.py.
  5. Re-run tests — both should pass.

Rationale: advisor cache keys (wave hashes) include ADVISOR_PROMPT_VERSION
to invalidate old cached verdicts when the prompt changes. This test
guards against accidentally changing the prompt without bumping the version.
"""

import hashlib
from pathlib import Path

import pytest

EXPECTED_BUG_SCANNER_PROMPT_SHA256 = "1193ffec333912585c42b9bf9a901b984b776209c46cbbab48c71fb436eb614c"
"""Pinned SHA256 of bug-scanner.md system prompt body (excluding YAML frontmatter)."""


def strip_yaml_frontmatter(text: str) -> str:
    """Strip leading YAML frontmatter from markdown content.

    Args:
        text: Full file content with optional YAML front matter.

    Returns:
        Content after the closing --- or the full text if no frontmatter.
    """
    lines = text.split("\n", maxsplit=1)
    if not lines[0].startswith("---"):
        return text
    remainder = lines[1] if len(lines) > 1 else ""
    parts = remainder.split("\n---\n", maxsplit=1)
    return parts[1] if len(parts) > 1 else remainder


def test_bug_scanner_prompt_version() -> None:
    """Load bug-scanner prompt, compute SHA256, assert against pinned constant.

    Skips if the agent file is not installed (e.g., on CI before install step).
    """
    agent_path = Path.home() / ".claude" / "agents" / "bug-scanner.md"

    if not agent_path.exists():
        pytest.skip(f"Agent not installed: {agent_path}")

    content = agent_path.read_text(encoding="utf-8")
    body = strip_yaml_frontmatter(content)
    actual_hash = hashlib.sha256(body.encode()).hexdigest()

    assert actual_hash == EXPECTED_BUG_SCANNER_PROMPT_SHA256, (
        f"bug-scanner prompt body has changed.\n"
        f"  Expected: {EXPECTED_BUG_SCANNER_PROMPT_SHA256}\n"
        f"  Actual:   {actual_hash}\n"
        f"See test docstring for manual bump procedure."
    )
