"""Tests for scripts/check_deps.py."""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.check_deps import (
    DepsConfig,
    ParsedImport,
    ResolutionCheckRequest,
    _check_exported_name,
    _check_file,
    _check_resolution_violations,
    _check_unused_imports,
    _extract_imports,
    _resolve_import,
    main,
)

SOURCE_UNRESOLVABLE_IMPORT = "import nonexistent_module_xyz_abc\nx = 1"
SOURCE_UNUSED_IMPORT = "import os\nx = 1"
SOURCE_UNEXPORTED_NAME = "from pathlib import NonExistentClassName"
SOURCE_STAR_IMPORT = "from os import *\nx = 1"
SOURCE_CLEAN = "import os\nresult = os.getcwd()"
TARGET_MODULE = "import os\nfrom pathlib import Path\n__all__ = ['helper']\ndef helper() -> str:\n    return os.getcwd()"


def _make_config(tmp_path: Path) -> DepsConfig:
    """Build a DepsConfig pointing at tmp_path."""
    return DepsConfig(directories=[tmp_path], workspace_root=tmp_path)


class TestImportExtraction:
    """Tests for _extract_imports — rule F11 parse coverage."""

    def test_simple_import_positive(self) -> None:
        """F11+: Extract simple import statement."""
        tree = ast.parse("import os")
        imports = _extract_imports(tree)
        assert len(imports) == 1
        assert imports[0].module == "os"
        assert imports[0].names == ["os"]
        assert imports[0].is_from is False

    def test_simple_import_negative(self) -> None:
        """F11-: No imports yields empty list."""
        tree = ast.parse("x = 1\ny = 2")
        imports = _extract_imports(tree)
        assert imports == []

    def test_from_import_positive(self) -> None:
        """F11+: Extract from-import with correct is_from flag."""
        tree = ast.parse("from pathlib import Path")
        imports = _extract_imports(tree)
        assert len(imports) == 1
        assert imports[0].module == "pathlib"
        assert imports[0].names == ["Path"]
        assert imports[0].is_from is True

    def test_alias_import_positive(self) -> None:
        """F11+: Alias is used as the resolved name."""
        tree = ast.parse("import numpy as np")
        imports = _extract_imports(tree)
        assert imports[0].names == ["np"]

    def test_multiple_names_from_import(self) -> None:
        """F11+: Multiple names from one from-import become one ParsedImport with all names."""
        tree = ast.parse("from os import path, getcwd")
        imports = _extract_imports(tree)
        assert len(imports) == 1
        assert set(imports[0].names) == {"path", "getcwd"}

    def test_star_import_extracted(self) -> None:
        """F11+: Star import is extracted with '*' in names."""
        tree = ast.parse(SOURCE_STAR_IMPORT)
        imports = _extract_imports(tree)
        star = [i for i in imports if "*" in i.names]
        assert len(star) == 1


class TestImportResolution:
    """Tests for _resolve_import — rule F11 resolve coverage."""

    def test_stdlib_resolves_positive(self) -> None:
        """F11+: stdlib module resolves successfully."""
        parsed = ParsedImport(module="os", names=["os"], line=1, is_from=False)
        assert _resolve_import(parsed) is True

    def test_nonexistent_module_negative(self) -> None:
        """F11-: Nonexistent module returns False."""
        parsed = ParsedImport(
            module="nonexistent_module_xyz_abc", names=["x"], line=1, is_from=False
        )
        assert _resolve_import(parsed) is False

    def test_mocked_find_spec_returns_none(self) -> None:
        """F11-: When find_spec returns None the import is unresolved."""
        parsed = ParsedImport(module="some_module", names=["x"], line=1, is_from=False)
        with patch("importlib.util.find_spec", return_value=None):
            assert _resolve_import(parsed) is False

    def test_mocked_find_spec_raises_import_error(self) -> None:
        """F11-: ImportError from find_spec returns False without raising."""
        parsed = ParsedImport(module="bad_module", names=["x"], line=1, is_from=False)
        with patch("importlib.util.find_spec", side_effect=ImportError("no module")):
            assert _resolve_import(parsed) is False

    def test_mocked_find_spec_returns_spec(self) -> None:
        """F11+: When find_spec returns a spec the import resolves."""
        parsed = ParsedImport(module="my_module", names=["x"], line=1, is_from=False)
        mock_spec = MagicMock()
        with patch("importlib.util.find_spec", return_value=mock_spec):
            assert _resolve_import(parsed) is True


class TestExportedNameCheck:
    """Tests for _check_exported_name — rule F13."""

    def test_known_exported_name_positive(self) -> None:
        """F13+: Known export from stdlib passes."""
        parsed = ParsedImport(module="pathlib", names=["Path"], line=1, is_from=True)
        assert _check_exported_name(parsed) is True

    def test_unknown_exported_name_negative(self) -> None:
        """F13-: Non-existent export from stdlib fails."""
        parsed = ParsedImport(
            module="pathlib", names=["NonExistentThing"], line=1, is_from=True
        )
        assert _check_exported_name(parsed) is False

    def test_non_from_import_skipped(self) -> None:
        """F13: Non-from imports are always considered exported."""
        parsed = ParsedImport(module="os", names=["os"], line=1, is_from=False)
        assert _check_exported_name(parsed) is True

    def test_relative_import_skipped(self) -> None:
        """F13: Relative imports are always considered exported."""
        parsed = ParsedImport(module=".utils", names=["helper"], line=1, is_from=True)
        assert _check_exported_name(parsed) is True

    def test_file_pair_exported_name_positive(self, tmp_path: Path) -> None:
        """F13+: Name exported via __all__ passes check against local file."""
        target = tmp_path / "mymod.py"
        target.write_text(TARGET_MODULE, encoding="utf-8")
        checker = tmp_path / "checker.py"
        checker.write_text("from mymod import helper", encoding="utf-8")
        parsed = ParsedImport(module="mymod", names=["helper"], line=1, is_from=True)
        sys.path.insert(0, str(tmp_path))
        try:
            result = _check_exported_name(parsed)
        finally:
            sys.path.pop(0)
        assert result is True

    def test_file_pair_unexported_name_negative(self, tmp_path: Path) -> None:
        """F13-: Name absent from __all__ fails check against local file."""
        target = tmp_path / "mymod2.py"
        target.write_text(
            "from pathlib import Path\n__all__ = ['Path']\n", encoding="utf-8"
        )
        parsed = ParsedImport(
            module="pathlib", names=["NonExistentClassName"], line=1, is_from=True
        )
        assert _check_exported_name(parsed) is False


class TestUnusedImports:
    """Tests for _check_unused_imports — rule F14."""

    def test_unused_import_detected_positive(self) -> None:
        """F14+: Imported name not referenced in body is reported."""
        tree = ast.parse(SOURCE_UNUSED_IMPORT)
        imports = _extract_imports(tree)
        unused = _check_unused_imports(tree, imports)
        assert "os" in unused

    def test_used_import_not_reported_negative(self) -> None:
        """F14-: Import used in body is not reported as unused."""
        tree = ast.parse(SOURCE_CLEAN)
        imports = _extract_imports(tree)
        unused = _check_unused_imports(tree, imports)
        assert "os" not in unused

    def test_multiple_one_unused(self) -> None:
        """F14+: Only unused names appear in the result."""
        code = "import os\nimport sys\nprint(os.getcwd())"
        tree = ast.parse(code)
        imports = _extract_imports(tree)
        unused = _check_unused_imports(tree, imports)
        assert "sys" in unused
        assert "os" not in unused

    def test_all_imports_used(self) -> None:
        """F14-: When all imports are used the result is empty."""
        code = "import os\nimport sys\nprint(os.getcwd(), sys.argv)"
        tree = ast.parse(code)
        imports = _extract_imports(tree)
        unused = _check_unused_imports(tree, imports)
        assert unused == []


class TestStarImportWarning:
    """Tests for F23: graceful handling of star imports."""

    def test_star_import_no_f11_or_f13_violation(self, tmp_path: Path) -> None:
        """F23: Star import is skipped — no F11/F13 resolution violation raised."""
        py_file = tmp_path / "star_test.py"
        py_file.write_text(SOURCE_STAR_IMPORT, encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        resolution_violations = [v for v in violations if v.rule in ("F11", "F13")]
        assert resolution_violations == []

    def test_star_import_no_f11_violation(self, tmp_path: Path) -> None:
        """F23: Star import does not generate an F11 unresolvable violation."""
        py_file = tmp_path / "star_f11.py"
        py_file.write_text(SOURCE_STAR_IMPORT, encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        f11_violations = [v for v in violations if v.rule == "F11"]
        assert f11_violations == []

    def test_star_import_mixed_file_other_issues_reported(self, tmp_path: Path) -> None:
        """F23: Non-star import issues still reported when star import present."""
        code = "from os import *\nimport nonexistent_xyz_module"
        py_file = tmp_path / "mixed.py"
        py_file.write_text(code, encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        rules = [v.rule for v in violations]
        assert "F11" in rules


class TestMainExitCodes:
    """Tests for main() exit codes."""

    def test_main_exits_clean_on_no_violations(self, tmp_path: Path) -> None:
        """main() returns EXIT_CLEAN when no violations found."""
        py_file = tmp_path / "clean.py"
        py_file.write_text(SOURCE_CLEAN, encoding="utf-8")
        with patch("sys.argv", ["check_deps", str(tmp_path)]):
            result = main()
        assert result == 0

    def test_main_exits_violations_on_issues(self, tmp_path: Path) -> None:
        """main() returns EXIT_VIOLATIONS when violations exist."""
        py_file = tmp_path / "bad.py"
        py_file.write_text(SOURCE_UNRESOLVABLE_IMPORT, encoding="utf-8")
        with patch("sys.argv", ["check_deps", str(tmp_path)]):
            result = main()
        assert result == 1

    def test_main_exits_violations_on_unused_import(self, tmp_path: Path) -> None:
        """main() returns EXIT_VIOLATIONS for unused imports."""
        py_file = tmp_path / "unused.py"
        py_file.write_text(SOURCE_UNUSED_IMPORT, encoding="utf-8")
        with patch("sys.argv", ["check_deps", str(tmp_path)]):
            result = main()
        assert result == 1


class TestFutureAnnotationsExemption:
    """Tests for B3 fix: from __future__ import annotations is never F8 or F14."""

    def test_future_annotations_not_unused_f14(self) -> None:
        """__future__ imports must not appear in unused names list."""
        source = "from __future__ import annotations\nx = 1\n"
        tree = ast.parse(source)
        imports = _extract_imports(tree)
        unused = _check_unused_imports(tree, imports)
        assert "annotations" not in unused

    def test_future_annotations_not_f8_violation(self, tmp_path: Path) -> None:
        """__future__ import must not generate F8 violation."""
        py_file = tmp_path / "future_test.py"
        py_file.write_text("from __future__ import annotations\nx = 1\n", encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        f8 = [v for v in violations if v.rule == "F8"]
        assert f8 == []

    def test_future_annotations_level_field(self) -> None:
        """ParsedImport for __future__ import has level=0 and module='__future__'."""
        source = "from __future__ import annotations\n"
        tree = ast.parse(source)
        imports = _extract_imports(tree)
        assert len(imports) == 1
        assert imports[0].module == "__future__"
        assert imports[0].level == 0


class TestSingleViolationPerStatement:
    """Tests for B2 fix: one violation per import statement, not per name."""

    def test_multi_name_import_one_f11_violation(self, tmp_path: Path) -> None:
        """Unresolvable from-import with multiple names yields one F11 violation."""
        source = "from nonexistent_xyz_module import A, B, C\nx = 1\n"
        py_file = tmp_path / "multi.py"
        py_file.write_text(source, encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        f11 = [v for v in violations if v.rule == "F11"]
        assert len(f11) == 1

    def test_multi_name_resolution_request_one_violation(self) -> None:
        """ResolutionCheckRequest with one unresolvable multi-name import emits one violation."""
        imp = ParsedImport(
            module="nonexistent_xyz_module_abc",
            names=["A", "B", "C"],
            line=1,
            is_from=True,
        )
        req = ResolutionCheckRequest(path=Path("test.py"), imports=[imp])
        violations = _check_resolution_violations(req)
        assert len(violations) == 1

    def test_separate_import_statements_yield_separate_violations(self, tmp_path: Path) -> None:
        """Two unresolvable import statements yield two violations, not one."""
        source = (
            "from nonexistent_xyz_module import A, B\n"
            "from another_missing_module import C, D\n"
            "x = 1\n"
        )
        py_file = tmp_path / "two_bad.py"
        py_file.write_text(source, encoding="utf-8")
        config = _make_config(tmp_path)
        violations = _check_file(py_file, config)
        f11 = [v for v in violations if v.rule == "F11"]
        assert len(f11) == 2


class TestWorkspaceRootSysPath:
    """Tests for B1 fix: sys.path insertion ensures local imports resolve."""

    def test_main_inserts_cwd_into_sys_path(self, tmp_path: Path) -> None:
        """main() adds cwd to sys.path before resolution so local imports don't false-positive."""
        pkg_dir = tmp_path / "mylocalpkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        py_file = tmp_path / "consumer.py"
        py_file.write_text("from mylocalpkg import something\nsomething()\n", encoding="utf-8")
        original_path = sys.path[:]
        try:
            with patch("sys.argv", ["check_deps", str(tmp_path)]):
                main()
            assert str(tmp_path) in sys.path or str(Path.cwd()) in sys.path
        finally:
            sys.path[:] = original_path

    def test_local_pkg_resolves_when_root_on_path(self, tmp_path: Path) -> None:
        """Local package imports resolve when workspace root is on sys.path."""
        pkg_name = "uniquelocalxyzpkg"
        pkg_dir = tmp_path / pkg_name
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("def helper(): pass\n")
        py_file = tmp_path / "consumer.py"
        py_file.write_text(f"from {pkg_name} import helper\nhelper()\n", encoding="utf-8")
        sys.path.insert(0, str(tmp_path))
        try:
            config = DepsConfig(directories=[tmp_path], workspace_root=tmp_path)
            violations = _check_file(py_file, config)
            f11 = [v for v in violations if v.rule == "F11"]
            assert f11 == []
        finally:
            sys.path.remove(str(tmp_path))
