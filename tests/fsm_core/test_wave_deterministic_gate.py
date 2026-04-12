"""Tests for wave_deterministic_gate module."""

import unittest
from unittest.mock import patch, MagicMock

from src.fsm_core.wave_deterministic_gate import (
    evaluate_wave,
    GATE_APPROVE,
    GATE_UNDETERMINED,
)


class TestWaveDeterministicGate(unittest.TestCase):
    """Test suite for deterministic wave evaluation."""

    @patch("src.fsm_core.wave_deterministic_gate.subprocess.run")
    def test_evaluate_wave_approves_on_all_clean(self, mock_run: MagicMock) -> None:
        """Test APPROVE verdict when all three checks return 0."""
        mock_run.return_value.returncode = 0
        task_paths = ("/abs/task_1.md", "/abs/task_2.md")

        with patch(
            "src.fsm_core.wave_deterministic_gate._derive_touched_files"
        ) as mock_derive:
            mock_derive.return_value = ("tests/foo.py", "src/bar.ts")
            result = evaluate_wave(task_paths)

        assert result.verdict == GATE_APPROVE
        assert "all deterministic checks passed" in result.detail
        assert result.touched_files == ("tests/foo.py", "src/bar.ts")
        assert mock_run.call_count == 3

    @patch("src.fsm_core.wave_deterministic_gate.subprocess.run")
    def test_evaluate_wave_undetermined_on_audit_fail(
        self, mock_run: MagicMock
    ) -> None:
        """Test UNDETERMINED when audit_discipline returns nonzero."""
        mock_run.return_value.returncode = 1
        task_paths = ("/abs/task_1.md",)

        with patch(
            "src.fsm_core.wave_deterministic_gate._derive_touched_files"
        ) as mock_derive:
            mock_derive.return_value = ("src/file.py",)
            result = evaluate_wave(task_paths)

        assert result.verdict == GATE_UNDETERMINED
        assert "discipline audit failed" in result.detail
        assert result.touched_files == ("src/file.py",)
        assert mock_run.call_count == 1
        assert "audit_discipline" in str(mock_run.call_args_list[0])

    @patch("src.fsm_core.wave_deterministic_gate.subprocess.run")
    def test_evaluate_wave_undetermined_on_pytest_fail(
        self, mock_run: MagicMock
    ) -> None:
        """Test UNDETERMINED when pytest returns nonzero."""
        side_effects = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=1),
        ]
        mock_run.side_effect = side_effects
        task_paths = ("/abs/task_1.md",)

        with patch(
            "src.fsm_core.wave_deterministic_gate._derive_touched_files"
        ) as mock_derive:
            mock_derive.return_value = ("tests/test_file.py", "src/impl.py")
            result = evaluate_wave(task_paths)

        assert result.verdict == GATE_UNDETERMINED
        assert "pytest failed" in result.detail
        assert result.touched_files == ("tests/test_file.py", "src/impl.py")
        assert mock_run.call_count == 3


if __name__ == "__main__":
    unittest.main()
