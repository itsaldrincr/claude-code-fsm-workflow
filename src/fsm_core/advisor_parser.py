import re
from dataclasses import dataclass


MAX_REVISE_ROUNDS = 3
REVISE_PATTERN = r"^REVISE round (\d+)"
UNPARSEABLE_TRUNCATE_LIMIT = 200


@dataclass
class AdvisorVerdict:
    is_approve: bool
    guidance: str


@dataclass
class ReviseEntryConfig:
    round_number: int
    nonce: str
    summary: str


def parse_advisor_output(stdout: str) -> AdvisorVerdict:
    """Parse advisor stdout to extract APPROVE or REVISE verdict."""
    lines = [line.strip() for line in stdout.split("\n") if line.strip()]
    if not lines:
        return AdvisorVerdict(is_approve=False, guidance="Unparseable advisor output: empty response")
    first_line = lines[0]
    if first_line.startswith("APPROVE"):
        return AdvisorVerdict(is_approve=True, guidance="")
    if first_line.startswith("REVISE"):
        remaining = "\n".join(lines[1:]) if len(lines) > 1 else ""
        return AdvisorVerdict(is_approve=False, guidance=remaining)
    truncated = stdout[:UNPARSEABLE_TRUNCATE_LIMIT]
    return AdvisorVerdict(
        is_approve=False,
        guidance=f"Unparseable advisor output: {truncated}",
    )


def build_revise_register_entry(config: ReviseEntryConfig) -> str:
    """Build formatted REVISE register entry string."""
    return f"REVISE round {config.round_number} (nonce {config.nonce}): {config.summary}"


def count_revise_rounds(registers_text: str) -> int:
    """Count REVISE round entries in registers text."""
    matches = re.findall(REVISE_PATTERN, registers_text, re.MULTILINE)
    return len(matches)


TASK_ID_PATTERN = r"task_\d{3}[a-z]?"
FAILING_TASKS_LINE_PATTERN = r"^FAILING TASKS:\s*(.+)$"


def extract_flagged_task_ids(guidance: str, candidates: list[str]) -> list[str]:
    """Extract task_ids the advisor flagged as failing in REVISE guidance.

    Prefers an explicit `FAILING TASKS: task_NNNa, task_NNNb, ...` line if present
    (the advisor prompt requires this). Falls back to free-text scanning for any
    `task_NNN[a-z]?` mention if the explicit line is missing. Returns task_ids from
    `candidates` only, preserving candidate order and deduplicated.
    """
    explicit = _parse_failing_tasks_line(guidance)
    if explicit:
        return [tid for tid in candidates if tid in explicit]
    mentioned = set(re.findall(TASK_ID_PATTERN, guidance))
    return [tid for tid in candidates if tid in mentioned]


def _parse_failing_tasks_line(guidance: str) -> set[str]:
    """Return set of task_ids from a `FAILING TASKS: ...` line, or empty set."""
    match = re.search(FAILING_TASKS_LINE_PATTERN, guidance, re.MULTILINE)
    if not match:
        return set()
    return set(re.findall(TASK_ID_PATTERN, match.group(1)))
