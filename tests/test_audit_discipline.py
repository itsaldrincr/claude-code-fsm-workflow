"""Tests for audit_discipline.py covering rules F1-F10 and F22."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.audit_discipline import (
    AuditConfig,
    FileContext,
    Violation,
    _audit_file,
    _check_annassign_bool,
    _check_import_order,
    _check_unused_imports,
    _classify_import,
    _count_body_lines,
    _is_local_import,
    _is_public_method,
    _parse_file,
    _walk_python_files,
    check_file,
)
from scripts.audit_discipline import _DisciplineVisitor

SOURCE_TOO_MANY_PARAMS = "def foo(a: int, b: int, c: int) -> int:\n    return a + b + c\n"

SOURCE_LONG_FUNCTION = (
    "def foo() -> int:\n"
    + "".join(f"    x{i} = {i}\n" for i in range(25))
    + "    return 0\n"
)

SOURCE_TOO_MANY_PUBLIC_METHODS = (
    "class A:\n"
    "    def foo(self) -> None: pass\n"
    "    def bar(self) -> None: pass\n"
    "    def baz(self) -> None: pass\n"
    "    def qux(self) -> None: pass\n"
)

SOURCE_BAD_CONSTANT_NAME = "max_size = 100\n"

SOURCE_MISSING_TYPE_HINTS = "def foo(a) -> int:\n    return a\n"

SOURCE_PRINT_CALL = "print('hello')\n"

SOURCE_UNUSED_IMPORT = "import os\nx = 1\n"

SOURCE_BAD_IMPORT_ORDER = "import pytest\nimport sys\n"

SOURCE_BARE_EXCEPT = "try:\n    x = 1\nexcept:\n    pass\n"

SOURCE_SILENT_EXCEPT = "try:\n    x = 1\nexcept ValueError:\n    pass\n"

SOURCE_BOOL_NO_PREFIX = "valid = True\n"

SOURCE_CLEAN = (
    "import logging\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "MAX_SIZE = 100\n"
    "\n"
    "\n"
    "def compute(value: int) -> int:\n"
    "    return value * MAX_SIZE\n"
)

SOURCE_SYNTAX_ERROR = "def foo(: pass\n"


def _make_config(tmp_path: Path) -> AuditConfig:
    """Build a default AuditConfig rooted at tmp_path."""
    return AuditConfig(directories=[tmp_path], workspace_root=tmp_path)


def _parse_source(source: str) -> FileContext:
    """Parse source string into FileContext."""
    tree = ast.parse(source)
    return FileContext(path=Path("test.py"), tree=tree)


def _violations_for(source: str, rule: str) -> list[Violation]:
    """Run discipline visitor on source, return violations for given rule."""
    ctx = _parse_source(source)
    config = AuditConfig(directories=[], workspace_root=Path("."))
    visitor = _DisciplineVisitor(config)
    visitor.visit(ctx.tree)
    extra = _check_unused_imports(ctx.tree)
    extra.extend(_check_import_order(ctx.tree, Path(".")))
    return [v for v in visitor.violations + extra if v.rule == rule]


class TestParamCount:
    """Test F1: max 2 parameters per function."""

    def test_two_params_passes(self) -> None:
        """Function with 2 params raises no F1 violation."""
        source = "def foo(a: int, b: int) -> int: return a + b\n"
        assert _violations_for(source, "F1") == []

    def test_three_params_fails(self) -> None:
        """Function with 3 params raises F1 violation."""
        assert len(_violations_for(SOURCE_TOO_MANY_PARAMS, "F1")) == 1

    def test_self_excluded_from_count(self) -> None:
        """self + 2 params does not violate F1."""
        source = "class A:\n    def foo(self, a: int, b: int) -> int: return a + b\n"
        assert _violations_for(source, "F1") == []


class TestBodyLength:
    """Test F2: max 20 body lines per function."""

    def test_short_body_passes(self) -> None:
        """Function with 3 lines passes F2."""
        source = "def foo() -> int:\n    x = 1\n    y = 2\n    return x + y\n"
        assert _violations_for(source, "F2") == []

    def test_long_body_fails(self) -> None:
        """Function with 26 body lines violates F2."""
        assert len(_violations_for(SOURCE_LONG_FUNCTION, "F2")) == 1


class TestPublicMethods:
    """Test F3: max 3 public methods per class."""

    def test_three_methods_passes(self) -> None:
        """Class with 3 public methods passes F3."""
        source = (
            "class A:\n"
            "    def foo(self) -> None: pass\n"
            "    def bar(self) -> None: pass\n"
            "    def baz(self) -> None: pass\n"
        )
        assert _violations_for(source, "F3") == []

    def test_four_methods_fails(self) -> None:
        """Class with 4 public methods violates F3."""
        assert len(_violations_for(SOURCE_TOO_MANY_PUBLIC_METHODS, "F3")) == 1


class TestConstantNaming:
    """Test F4: numeric constants must be UPPER_SNAKE_CASE."""

    def test_upper_constant_passes(self) -> None:
        """UPPER_SNAKE_CASE numeric constant passes F4."""
        assert _violations_for("MAX_SIZE = 100\n", "F4") == []

    def test_lower_numeric_fails(self) -> None:
        """Lowercase numeric constant violates F4."""
        assert len(_violations_for(SOURCE_BAD_CONSTANT_NAME, "F4")) == 1

    def test_zero_and_one_exempt(self) -> None:
        """Magic numbers 0 and 1 are exempt from F4."""
        assert _violations_for("count = 0\nflag = 1\n", "F4") == []


class TestTypeHints:
    """Test F6: all function params and return types need type hints."""

    def test_full_hints_passes(self) -> None:
        """Fully typed function passes F6."""
        source = "def foo(a: int, b: str) -> str: return str(a) + b\n"
        assert _violations_for(source, "F6") == []

    def test_missing_param_hint_fails(self) -> None:
        """Untyped param violates F6."""
        assert len(_violations_for(SOURCE_MISSING_TYPE_HINTS, "F6")) >= 1

    def test_missing_return_hint_fails(self) -> None:
        """Missing return hint violates F6."""
        source = "def foo(a: int): return a\n"
        assert len(_violations_for(source, "F6")) >= 1


class TestPrintCalls:
    """Test F7: no print() calls allowed."""

    def test_no_print_passes(self) -> None:
        """Code using logging.info passes F7."""
        source = "import logging\nlogging.info('hello')\n"
        assert _violations_for(source, "F7") == []

    def test_print_call_fails(self) -> None:
        """Direct print() call violates F7."""
        assert len(_violations_for(SOURCE_PRINT_CALL, "F7")) == 1


class TestUnusedImports:
    """Test F8: imported names must be used."""

    def test_used_import_passes(self) -> None:
        """Import that is referenced passes F8."""
        source = "import os\nx = os.getcwd()\n"
        assert _violations_for(source, "F8") == []

    def test_unused_import_fails(self) -> None:
        """Import that is never referenced violates F8."""
        assert len(_violations_for(SOURCE_UNUSED_IMPORT, "F8")) == 1

    def test_unused_from_import_fails(self) -> None:
        """from-import that is never used violates F8."""
        source = "from pathlib import Path\nx = 1\n"
        assert len(_violations_for(source, "F8")) == 1


class TestImportOrder:
    """Test F9: imports must be grouped stdlib → third-party → local."""

    def test_correct_order_passes(self) -> None:
        """stdlib import before third-party passes F9."""
        source = "import sys\nimport pytest\n"
        assert _violations_for(source, "F9") == []

    def test_stdlib_after_third_party_fails(self) -> None:
        """stdlib import appearing after third-party violates F9."""
        assert len(_violations_for(SOURCE_BAD_IMPORT_ORDER, "F9")) >= 1


class TestExceptionHandling:
    """Test F10: no bare except or except with only pass."""

    def test_typed_except_with_code_passes(self) -> None:
        """Typed except with real code passes F10."""
        source = "try:\n    x = 1\nexcept ValueError as e:\n    raise\n"
        assert _violations_for(source, "F10") == []

    def test_bare_except_fails(self) -> None:
        """Bare except clause violates F10."""
        assert len(_violations_for(SOURCE_BARE_EXCEPT, "F10")) >= 1

    def test_silent_except_fails(self) -> None:
        """Except with only pass violates F10."""
        assert len(_violations_for(SOURCE_SILENT_EXCEPT, "F10")) == 1


class TestBooleanNaming:
    """Test F5: boolean variables must start with is_/has_/should_."""

    def test_is_prefix_passes(self) -> None:
        """Boolean with is_ prefix passes F5."""
        assert _violations_for("is_valid = True\n", "F5") == []

    def test_has_prefix_passes(self) -> None:
        """Boolean with has_ prefix passes F5."""
        assert _violations_for("has_data = False\n", "F5") == []

    def test_should_prefix_passes(self) -> None:
        """Boolean with should_ prefix passes F5."""
        assert _violations_for("should_retry = True\n", "F5") == []

    def test_no_prefix_fails(self) -> None:
        """Boolean without required prefix violates F5."""
        assert len(_violations_for(SOURCE_BOOL_NO_PREFIX, "F5")) == 1

    def test_annassign_bool_with_prefix_passes(self) -> None:
        """Annotated bool with is_ prefix passes F5."""
        source = "is_loaded: bool = True\n"
        assert _violations_for(source, "F5") == []

    def test_annassign_bool_without_prefix_fails(self) -> None:
        """Annotated bool without required prefix violates F5."""
        source = "loaded: bool = True\n"
        assert len(_violations_for(source, "F5")) == 1


class TestSyntaxErrorSkip:
    """Test F22: files with syntax errors are skipped gracefully."""

    def test_syntax_error_returns_f0_violation(self, tmp_path: Path) -> None:
        """_audit_file returns a synthetic F0 violation for files with syntax errors."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_SYNTAX_ERROR, encoding="utf-8")
        config = _make_config(tmp_path)
        result = _audit_file(bad_file, config)
        assert len(result) == 1
        assert result[0].rule == "F0"
        assert result[0].line == 0
        assert "syntax error" in result[0].detail

    def test_syntax_error_does_not_raise(self, tmp_path: Path) -> None:
        """_parse_file returns None (not exception) on syntax error."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_SYNTAX_ERROR, encoding="utf-8")
        ctx = _parse_file(bad_file)
        assert ctx is None

    def test_good_file_alongside_bad_is_audited(self, tmp_path: Path) -> None:
        """A valid file is still audited even when a bad file exists."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_SYNTAX_ERROR, encoding="utf-8")
        good_file = tmp_path / "good.py"
        good_file.write_text(SOURCE_PRINT_CALL, encoding="utf-8")
        config = _make_config(tmp_path)
        bad_result = _audit_file(bad_file, config)
        good_result = _audit_file(good_file, config)
        assert len(bad_result) == 1
        assert bad_result[0].rule == "F0"
        assert len(good_result) >= 1


class TestFutureAnnotationsF8Exempt:
    """Test B3 fix: from __future__ import annotations never triggers F8."""

    def test_future_annotations_no_f8(self) -> None:
        """from __future__ import annotations does not trigger F8 violation."""
        source = "from __future__ import annotations\nx = 1\n"
        assert _violations_for(source, "F8") == []

    def test_future_division_no_f8(self) -> None:
        """from __future__ import division does not trigger F8 violation."""
        source = "from __future__ import division\nx = 1.0 / 2\n"
        assert _violations_for(source, "F8") == []

    def test_non_future_unused_still_f8(self) -> None:
        """Regular unused imports still trigger F8 alongside __future__."""
        source = "from __future__ import annotations\nimport os\nx = 1\n"
        violations = _violations_for(source, "F8")
        assert len(violations) == 1
        assert "os" in violations[0].detail


class TestBoolIntCofire:
    """Test M5 fix: bool literals do not co-fire F4 and F5."""

    def test_bool_true_no_f4(self) -> None:
        """flag = True must not trigger F4 (numeric constant)."""
        assert _violations_for("flag = True\n", "F4") == []

    def test_bool_false_no_f4(self) -> None:
        """flag = False must not trigger F4."""
        assert _violations_for("flag = False\n", "F4") == []

    def test_bool_true_triggers_f5_only(self) -> None:
        """flag = True triggers exactly one F5 violation and no F4."""
        f4 = _violations_for("flag = True\n", "F4")
        f5 = _violations_for("flag = True\n", "F5")
        assert f4 == []
        assert len(f5) == 1


class TestImportOrderAlwaysUpdates:
    """Test M4 fix: import order check catches all out-of-order imports."""

    def test_multiple_out_of_order_all_reported(self) -> None:
        """All out-of-order imports after first violation are still reported."""
        source = "import pytest\nimport sys\nimport os\n"
        violations = _violations_for(source, "F9")
        assert len(violations) >= 2


class TestMainExitCodes:
    """Test that main() exits 0 (clean) or 1 (violations), never 2."""

    def test_exit_0_on_clean_dir(self, tmp_path: Path) -> None:
        """main() exits 0 when no violations found."""
        clean_file = tmp_path / "clean.py"
        clean_file.write_text(SOURCE_CLEAN, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/audit_discipline.py", str(tmp_path)],
            capture_output=True,
        )
        assert result.returncode == 0

    def test_exit_1_on_violations(self, tmp_path: Path) -> None:
        """main() exits 1 when violations are found."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_PRINT_CALL, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/audit_discipline.py", str(tmp_path)],
            capture_output=True,
        )
        assert result.returncode == 1

    def test_exit_not_2_on_syntax_error_file(self, tmp_path: Path) -> None:
        """main() does not exit 2 when a file has a syntax error (graceful skip)."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_SYNTAX_ERROR, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "scripts/audit_discipline.py", str(tmp_path)],
            capture_output=True,
        )
        assert result.returncode != 2


class TestCheckFilePublic:
    """Test check_file() public API for direct file auditing."""

    def test_check_file_returns_violations_for_bad_file(self, tmp_path: Path) -> None:
        """check_file() returns non-empty violation list for file with discipline violations."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(SOURCE_TOO_MANY_PARAMS, encoding="utf-8")
        violations = check_file(bad_file)
        assert len(violations) > 0
        assert any(v.rule == "F1" and "param" in v.detail for v in violations)

    def test_check_file_returns_empty_for_clean_file(self, tmp_path: Path) -> None:
        """check_file() returns empty list for file with no violations."""
        clean_file = tmp_path / "clean.py"
        clean_file.write_text(SOURCE_CLEAN, encoding="utf-8")
        violations = check_file(clean_file)
        assert violations == []
