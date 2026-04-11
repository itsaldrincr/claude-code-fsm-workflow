"""Tests for session_close.py."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.session_close import (
    AUDIT_SENTINEL,
    CLEAN_MAP_TEMPLATE,
    EXIT_CLEAN,
    EXIT_ERROR,
    EXIT_FAILED,
    PYTHON_EXECUTABLE,
    TEST_DIR,
    CloseConfig,
    CloseResult,
    _delete_sentinel,
    _delete_task_files,
    _parse_args,
    _reset_map,
    _run_close,
    _run_tests,
    main,
)


class TestCloseConfig:
    """Test CloseConfig dataclass."""

    def test_close_config_defaults(self) -> None:
        """CloseConfig with default is_dry_run=False."""
        config = CloseConfig(workspace=Path("."))
        assert config.workspace == Path(".")
        assert config.is_dry_run is False

    def test_close_config_frozen(self) -> None:
        """CloseConfig is frozen (immutable)."""
        config = CloseConfig(workspace=Path("."))
        with pytest.raises(AttributeError):
            config.is_dry_run = True


class TestCloseResult:
    """Test CloseResult dataclass."""

    def test_close_result_frozen(self) -> None:
        """CloseResult is frozen (immutable)."""
        result = CloseResult(exit_code=EXIT_CLEAN, detail="done")
        with pytest.raises(AttributeError):
            result.exit_code = EXIT_FAILED


class TestParseArgs:
    """Test _parse_args()."""

    def test_parse_args_defaults(self) -> None:
        """_parse_args with no args returns default workspace and is_dry_run=False."""
        with patch("sys.argv", ["session_close.py"]):
            config = _parse_args()
            assert config.workspace == Path(".")
            assert config.is_dry_run is False

    def test_parse_args_workspace(self) -> None:
        """_parse_args with --workspace arg."""
        with patch("sys.argv", ["session_close.py", "--workspace", "/tmp/workspace"]):
            config = _parse_args()
            assert config.workspace == Path("/tmp/workspace")
            assert config.is_dry_run is False

    def test_parse_args_dry_run(self) -> None:
        """_parse_args with --dry-run flag."""
        with patch("sys.argv", ["session_close.py", "--dry-run"]):
            config = _parse_args()
            assert config.is_dry_run is True


class TestRunTests:
    """Test _run_tests()."""

    def test_run_tests_success(self) -> None:
        """_run_tests returns successful CompletedProcess."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "tests").mkdir()
            (workspace / "tests" / "dummy.py").write_text("# dummy")

            with patch("subprocess.run") as mock_run:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 0
                mock_run.return_value = mock_proc

                result = _run_tests(workspace)
                assert result.returncode == 0
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                assert call_args[0][0] == [PYTHON_EXECUTABLE, "-m", "pytest", TEST_DIR, "-v"]
                assert call_args[1]["cwd"] == workspace

    def test_run_tests_failure(self) -> None:
        """_run_tests returns failed CompletedProcess."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            with patch("subprocess.run") as mock_run:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 1
                mock_run.return_value = mock_proc

                result = _run_tests(workspace)
                assert result.returncode == 1


class TestDeleteTaskFiles:
    """Test _delete_task_files()."""

    def test_delete_task_files_removes_files(self) -> None:
        """_delete_task_files deletes all task_*.md files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            task1 = workspace / "task_801.md"
            task2 = workspace / "task_802.md"
            other = workspace / "other.md"

            task1.write_text("# Task 1")
            task2.write_text("# Task 2")
            other.write_text("# Other")

            _delete_task_files(workspace)

            assert not task1.exists()
            assert not task2.exists()
            assert other.exists()

    def test_delete_task_files_empty_workspace(self) -> None:
        """_delete_task_files handles empty workspace gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            _delete_task_files(workspace)


class TestResetMap:
    """Test _reset_map()."""

    def test_reset_map_creates_file(self) -> None:
        """_reset_map creates MAP.md with clean template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            _reset_map(workspace)

            map_path = workspace / "MAP.md"
            assert map_path.exists()
            content = map_path.read_text()
            assert content == CLEAN_MAP_TEMPLATE

    def test_reset_map_overwrites_file(self) -> None:
        """_reset_map overwrites existing MAP.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            map_path = workspace / "MAP.md"
            map_path.write_text("old content")

            _reset_map(workspace)

            content = map_path.read_text()
            assert content == CLEAN_MAP_TEMPLATE


class TestDeleteSentinel:
    """Test _delete_sentinel()."""

    def test_delete_sentinel_removes_file(self) -> None:
        """_delete_sentinel removes .audit_clean if present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            sentinel_path = workspace / AUDIT_SENTINEL
            sentinel_path.write_text("clean")

            _delete_sentinel(workspace)

            assert not sentinel_path.exists()

    def test_delete_sentinel_missing_file(self) -> None:
        """_delete_sentinel handles missing .audit_clean gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            _delete_sentinel(workspace)


class TestRunClose:
    """Test _run_close()."""

    def test_run_close_tests_pass(self) -> None:
        """_run_close returns EXIT_CLEAN and performs cleanup when tests pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "MAP.md").write_text("old")
            task_file = workspace / "task_801.md"
            task_file.write_text("# Task")
            sentinel = workspace / AUDIT_SENTINEL
            sentinel.write_text("clean")

            config = CloseConfig(workspace=workspace, is_dry_run=False)
            with patch("scripts.session_close._run_tests") as mock_tests:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 0
                mock_tests.return_value = mock_proc

                result = _run_close(config)

                assert result.exit_code == EXIT_CLEAN
                assert not task_file.exists()
                assert not sentinel.exists()
                assert (workspace / "MAP.md").read_text() == CLEAN_MAP_TEMPLATE

    def test_run_close_tests_fail(self) -> None:
        """_run_close returns EXIT_FAILED and skips cleanup when tests fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "MAP.md").write_text("old")
            task_file = workspace / "task_801.md"
            task_file.write_text("# Task")

            config = CloseConfig(workspace=workspace, is_dry_run=False)
            with patch("scripts.session_close._run_tests") as mock_tests:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 1
                mock_tests.return_value = mock_proc

                result = _run_close(config)

                assert result.exit_code == EXIT_FAILED
                assert task_file.exists()
                assert (workspace / "MAP.md").read_text() == "old"

    def test_run_close_dry_run(self) -> None:
        """_run_close in dry-run mode logs but does not delete files or reset MAP."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "MAP.md").write_text("old")
            task_file = workspace / "task_801.md"
            task_file.write_text("# Task")

            config = CloseConfig(workspace=workspace, is_dry_run=True)
            with patch("scripts.session_close._run_tests") as mock_tests:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 0
                mock_tests.return_value = mock_proc

                result = _run_close(config)

                assert result.exit_code == EXIT_CLEAN
                assert task_file.exists()
                assert (workspace / "MAP.md").read_text() == "old"


class TestMain:
    """Test main()."""

    def test_main_tests_pass(self) -> None:
        """main exits with EXIT_CLEAN and performs cleanup when tests pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "MAP.md").write_text("old")
            task_file = workspace / "task_801.md"
            task_file.write_text("# Task")
            sentinel = workspace / AUDIT_SENTINEL
            sentinel.write_text("clean")

            with patch("scripts.session_close._run_tests") as mock_tests:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 0
                mock_tests.return_value = mock_proc

                with patch("sys.argv", ["session_close.py", "--workspace", str(workspace)]):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == EXIT_CLEAN
                    assert not task_file.exists()
                    assert not sentinel.exists()
                    assert (workspace / "MAP.md").read_text() == CLEAN_MAP_TEMPLATE

    def test_main_tests_fail(self) -> None:
        """main exits with EXIT_FAILED when tests fail and cleanup does not run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "MAP.md").write_text("old")
            task_file = workspace / "task_801.md"
            task_file.write_text("# Task")

            with patch("scripts.session_close._run_tests") as mock_tests:
                mock_proc = MagicMock(spec=subprocess.CompletedProcess)
                mock_proc.returncode = 1
                mock_tests.return_value = mock_proc

                with patch("sys.argv", ["session_close.py", "--workspace", str(workspace)]):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

                    assert exc_info.value.code == EXIT_FAILED
                    assert task_file.exists()
                    assert (workspace / "MAP.md").read_text() == "old"


class TestConstants:
    """Test module constants."""

    def test_clean_map_template_structure(self) -> None:
        """CLEAN_MAP_TEMPLATE contains expected sections."""
        assert "# MAP" in CLEAN_MAP_TEMPLATE
        assert "## Active Tasks" in CLEAN_MAP_TEMPLATE
        assert "## Completed (awaiting audit)" in CLEAN_MAP_TEMPLATE
        assert "## File Directory" in CLEAN_MAP_TEMPLATE
        assert "— none —" in CLEAN_MAP_TEMPLATE

    def test_exit_codes(self) -> None:
        """Exit codes are distinct integers."""
        assert EXIT_CLEAN == 0
        assert EXIT_FAILED == 1
        assert EXIT_ERROR == 2
        assert len({EXIT_CLEAN, EXIT_FAILED, EXIT_ERROR}) == 3

    def test_audit_sentinel(self) -> None:
        """AUDIT_SENTINEL is a string."""
        assert isinstance(AUDIT_SENTINEL, str)
        assert AUDIT_SENTINEL == ".audit_clean"

    def test_python_executable_is_string(self) -> None:
        """PYTHON_EXECUTABLE is a non-empty string."""
        assert isinstance(PYTHON_EXECUTABLE, str)
        assert len(PYTHON_EXECUTABLE) > 0

    def test_test_dir_is_string(self) -> None:
        """TEST_DIR is a string ending in slash."""
        assert isinstance(TEST_DIR, str)
        assert TEST_DIR.endswith("/")
