"""Unit tests for patch evaluation backend."""

import pytest

from bench.evaluate import EvaluationRequest, EvaluationResult, evaluate


def test_identical_patches_score_one():
    """Identical patches should score 1.0."""
    patch = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def foo():
+    pass
     return 42
"""
    request = EvaluationRequest(expected_patch=patch, captured_patch=patch, backend="local")
    result = evaluate(request)
    assert result.score == 1.0
    assert result.backend_used == "local"


def test_empty_captured_patch_score_zero():
    """Empty captured patch should score 0.0."""
    expected = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def foo():
+    pass
     return 42
"""
    request = EvaluationRequest(expected_patch=expected, captured_patch="", backend="local")
    result = evaluate(request)
    assert result.score == 0.0


def test_same_files_different_hunks_strictly_between():
    """Patches with same files but different hunks should score strictly between 0 and 1."""
    expected = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def foo():
+    pass
     return 42
"""
    captured = """--- a/test.py
+++ b/test.py
@@ -5,3 +5,4 @@
 def bar():
+    pass
     return 84
"""
    request = EvaluationRequest(expected_patch=expected, captured_patch=captured, backend="local")
    result = evaluate(request)
    assert 0.0 < result.score < 1.0
