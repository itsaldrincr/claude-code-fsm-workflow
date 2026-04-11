"""Patch evaluation backend: compare expected and captured patches using heuristics.

Provides pluggable backends: local (fast, heuristic-based) and official (requires swebench).
"""

from dataclasses import dataclass
from typing import Literal

# Evaluation weights (heuristic-based scoring).
FILE_MATCH_WEIGHT: float = 0.4
HUNK_MATCH_WEIGHT: float = 0.3
LINE_MATCH_WEIGHT: float = 0.3


@dataclass
class EvaluationRequest:
    """Request to evaluate similarity between expected and captured patches.

    Attributes:
        expected_patch: Expected patch content (string).
        captured_patch: Captured patch content (string).
        backend: Evaluation backend ("local" or "official").
    """

    expected_patch: str
    captured_patch: str
    backend: Literal["local", "official"]


@dataclass
class EvaluationResult:
    """Result of patch evaluation.

    Attributes:
        score: Similarity score in [0.0, 1.0]. 1.0 = identical, 0.0 = completely different.
        backend_used: Backend name that produced this result.
    """

    score: float
    backend_used: str


def evaluate(request: EvaluationRequest) -> EvaluationResult:
    """Evaluate similarity between expected and captured patches.

    Routes to the appropriate backend based on request.backend.
    """
    if request.backend == "local":
        return _evaluate_local(request)
    elif request.backend == "official":
        return _evaluate_official(request)
    else:
        raise ValueError(f"Unknown backend: {request.backend}")


def _evaluate_local(request: EvaluationRequest) -> EvaluationResult:
    """Local heuristic evaluation: tokenize patches, compare file/hunk/line counts."""
    file_score = _match_score(_extract_files(request.expected_patch), _extract_files(request.captured_patch))
    hunk_score = _match_score(_extract_hunks(request.expected_patch), _extract_hunks(request.captured_patch))
    line_score = _match_score(_count_lines(request.expected_patch), _count_lines(request.captured_patch))
    combined_score = (file_score * FILE_MATCH_WEIGHT + hunk_score * HUNK_MATCH_WEIGHT + line_score * LINE_MATCH_WEIGHT)
    return EvaluationResult(score=max(0.0, min(1.0, combined_score)), backend_used="local")


def _evaluate_official(request: EvaluationRequest) -> EvaluationResult:
    """Official evaluation stub.

    Requires swebench package. See: https://github.com/princeton-nlp/SWE-bench
    """
    raise NotImplementedError(
        "Official evaluation requires swebench. "
        "Install via: pip install swebench. "
        "See: https://github.com/princeton-nlp/SWE-bench"
    )


def _extract_files(patch: str) -> set[str]:
    """Extract file paths from patch (lines starting with '---' or '+++')."""
    files = set()
    for line in patch.split("\n"):
        if line.startswith("---") or line.startswith("+++"):
            parts = line.split("\t")
            if len(parts) > 0:
                file_path = parts[0][4:].strip()  # Remove '--- ' or '+++ '
                if file_path and file_path != "/dev/null":
                    files.add(file_path)
    return files


def _extract_hunks(patch: str) -> set[str]:
    """Extract hunk headers from patch (lines starting with '@@')."""
    hunks = set()
    for line in patch.split("\n"):
        if line.startswith("@@"):
            hunks.add(line.strip())
    return hunks


def _count_lines(patch: str) -> dict[str, int]:
    """Count added and removed lines in patch."""
    added = sum(1 for line in patch.split("\n") if line.startswith("+") and not line.startswith("+++"))
    removed = sum(
        1 for line in patch.split("\n") if line.startswith("-") and not line.startswith("---")
    )
    return {"added": added, "removed": removed}


def _match_score(expected: object, captured: object) -> float:
    """Compute similarity score between expected and captured values."""
    if expected == captured:
        return 1.0
    if isinstance(expected, dict) and isinstance(captured, dict):
        return _score_dicts(expected, captured)
    if isinstance(expected, set) and isinstance(captured, set):
        return _score_sets(expected, captured)
    return 0.0


def _score_dicts(expected: dict, captured: dict) -> float:
    """Score similarity of two dictionaries by value sum ratio."""
    if not expected and not captured:
        return 1.0
    if not expected or not captured:
        return 0.0
    exp_sum = sum(expected.values())
    cap_sum = sum(captured.values())
    if exp_sum == 0:
        return 0.0
    return min(cap_sum / exp_sum, exp_sum / cap_sum) if cap_sum > 0 else 0.0


def _score_sets(expected: set, captured: set) -> float:
    """Score similarity of two sets using Jaccard index."""
    if not expected and not captured:
        return 1.0
    if not expected or not captured:
        return 0.0
    intersection = len(expected & captured)
    union = len(expected | captured)
    return intersection / union if union > 0 else 0.0
