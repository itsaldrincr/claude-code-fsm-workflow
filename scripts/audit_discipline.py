"""Audit Python files for coding discipline violations per CLAUDE.md rules F1-F10, F22."""

import argparse
import ast
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

MAX_PARAMS = 2
MAX_BODY_LINES = 20
MAX_PUBLIC_METHODS = 3
BOOL_PREFIXES = ("is_", "has_", "should_")
EXIT_CLEAN = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2


@dataclass(frozen=True)
class Violation:
    """A single discipline violation found in a file."""

    file: str
    line: int
    scope: str
    rule: str
    detail: str


@dataclass(frozen=True)
class AuditConfig:
    """Configuration for the audit run."""

    directories: list[Path]
    workspace_root: Path


@dataclass(frozen=True)
class FileContext:
    """Parsed file with AST tree."""

    path: Path
    tree: ast.Module


def _parse_args() -> AuditConfig:
    """Parse command-line arguments and return AuditConfig."""
    parser = argparse.ArgumentParser(
        description="Audit Python files for coding discipline violations."
    )
    parser.add_argument(
        "directories",
        nargs="+",
        type=str,
        help="Directories to audit",
    )
    parser.add_argument(
        "--workspace-root",
        type=str,
        default=".",
        help="Workspace root for import classification",
    )
    args = parser.parse_args()
    dirs = [Path(d).resolve() for d in args.directories]
    ws_root = Path(args.workspace_root).resolve()
    return AuditConfig(directories=dirs, workspace_root=ws_root)


def _walk_python_files(directory: Path) -> Generator[Path, None, None]:
    """Yield all .py files in a directory recursively."""
    if not directory.exists():
        return
    for item in directory.rglob("*.py"):
        yield item


def _parse_file(path: Path) -> FileContext | None:
    """Parse a Python file and return FileContext, or None on SyntaxError."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        return FileContext(path=path, tree=tree)
    except SyntaxError as e:
        logger.warning("Syntax error in %s: %s", path, e)
        return None


def _classify_import(module_name: str, workspace_root: Path) -> str:
    """Classify import as 'stdlib', 'third-party', or 'local'."""
    top_level = module_name.split(".")[0]
    if top_level in sys.stdlib_module_names:
        return "stdlib"
    if _is_local_import(module_name, workspace_root):
        return "local"
    return "third-party"


def _is_local_import(module_name: str, workspace_root: Path) -> bool:
    """Check if module_name refers to local workspace code."""
    top_level = module_name.split(".")[0]
    try:
        spec = importlib.util.find_spec(top_level)
        if spec and spec.origin:
            origin_path = Path(spec.origin).resolve()
            return workspace_root in origin_path.parents or origin_path.parent == workspace_root
    except (ImportError, ValueError) as e:
        logger.debug("Could not find spec for %s: %s", top_level, e)
    return False


def _count_body_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count non-decorator lines in function body."""
    if not node.body:
        return 0
    first_stmt = node.body[0]
    last_stmt = node.body[-1]
    start = first_stmt.lineno
    end = last_stmt.end_lineno or first_stmt.lineno
    return end - start + 1


def _is_public_method(name: str) -> bool:
    """Return True if name is a public method (not dunder, not private)."""
    return not name.startswith("_")


def _check_function_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Violation]:
    """Check function parameter count (F1)."""
    params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    if len(params) <= MAX_PARAMS:
        return []
    detail = f"{len(params)} params (max {MAX_PARAMS})"
    return [Violation(file="<visitor>", line=node.lineno, scope=node.name, rule="F1", detail=detail)]


def _check_function_body_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Violation]:
    """Check function body line count (F2)."""
    body_lines = _count_body_lines(node)
    if body_lines <= MAX_BODY_LINES:
        return []
    detail = f"{body_lines} lines (max {MAX_BODY_LINES})"
    return [Violation(file="<visitor>", line=node.lineno, scope=node.name, rule="F2", detail=detail)]


def _check_param_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Violation]:
    """Check that all non-self params have type hints (F6 partial)."""
    violations: list[Violation] = []
    for arg in node.args.args:
        if arg.annotation is None and arg.arg not in ("self", "cls"):
            violations.append(Violation(
                file="<visitor>", line=node.lineno, scope=node.name,
                rule="F6", detail=f"param {arg.arg} missing type hint",
            ))
    return violations


def _check_function_type_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Violation]:
    """Check function type hints (F6)."""
    violations = _check_param_hints(node)
    if node.returns is None:
        violations.append(Violation(
            file="<visitor>", line=node.lineno, scope=node.name,
            rule="F6", detail="return type hint missing",
        ))
    return violations


def _check_assign_constant(name: str, node: ast.Assign) -> list[Violation]:
    """Check numeric constant naming (F4)."""
    if not isinstance(node.value, ast.Constant):
        return []
    if isinstance(node.value.value, bool):
        return []
    is_numeric = isinstance(node.value.value, (int, float))
    is_upper = name.isupper()
    is_private = name.startswith("_")
    is_exempt = node.value.value in (0, 1)
    if is_numeric and not is_upper and not is_private and not is_exempt:
        detail = f"numeric constant {name} should be UPPER_SNAKE_CASE"
        return [Violation(file="<visitor>", line=node.lineno, scope="<module>", rule="F4", detail=detail)]
    return []


def _check_assign_bool(name: str, node: ast.Assign) -> list[Violation]:
    """Check boolean variable naming (F5)."""
    is_bool_literal = isinstance(node.value, ast.Constant) and isinstance(node.value.value, bool)
    has_prefix = any(name.startswith(p) for p in BOOL_PREFIXES)
    if is_bool_literal and not has_prefix:
        detail = f"bool var {name} should start with is_/has_/should_"
        return [Violation(file="<visitor>", line=node.lineno, scope="<module>", rule="F5", detail=detail)]
    return []


def _check_annassign_bool(node: ast.AnnAssign) -> list[Violation]:
    """Check annotated bool assignment naming (F5): `name: bool = ...`."""
    is_bool_annotation = isinstance(node.annotation, ast.Name) and node.annotation.id == "bool"
    if not is_bool_annotation:
        return []
    if not isinstance(node.target, ast.Name):
        return []
    name = node.target.id
    has_prefix = any(name.startswith(p) for p in BOOL_PREFIXES)
    if has_prefix:
        return []
    detail = f"bool var {name} should start with is_/has_/should_"
    return [Violation(file="<visitor>", line=node.lineno, scope="<module>", rule="F5", detail=detail)]



def _collect_used_names(tree: ast.Module) -> set[str]:
    """Collect all Name references used in non-import statements."""
    used: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                used.add(child.id)
            elif isinstance(child, ast.Attribute):
                root = child
                while isinstance(root, ast.Attribute):
                    root = root.value  # type: ignore[assignment]
                if isinstance(root, ast.Name):
                    used.add(root.id)
    return used


def _unused_plain_import(node: ast.Import, used: set[str]) -> list[Violation]:
    """Check ast.Import node for unused names; return F8 violations."""
    violations: list[Violation] = []
    for alias in node.names:
        bound = alias.asname or alias.name.split(".")[0]
        if bound not in used:
            violations.append(Violation(
                file="<visitor>", line=node.lineno, scope="<module>",
                rule="F8", detail=f"unused import: {alias.name}",
            ))
    return violations


def _unused_from_import(node: ast.ImportFrom, used: set[str]) -> list[Violation]:
    """Check ast.ImportFrom node for unused names; return F8 violations."""
    if node.module == "__future__":
        return []
    violations: list[Violation] = []
    for alias in node.names:
        bound = alias.asname or alias.name
        if bound != "*" and bound not in used:
            violations.append(Violation(
                file="<visitor>", line=node.lineno, scope="<module>",
                rule="F8", detail=f"unused import: {alias.name}",
            ))
    return violations


def _unused_from_import_node(node: ast.Import | ast.ImportFrom, used: set[str]) -> list[Violation]:
    """Check one import node for unused names; return F8 violations."""
    if isinstance(node, ast.Import):
        return _unused_plain_import(node, used)
    return _unused_from_import(node, used)


def _check_unused_imports(tree: ast.Module) -> list[Violation]:
    """Check for unused imports at module level (F8)."""
    used = _collect_used_names(tree)
    violations: list[Violation] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_unused_from_import_node(node, used))
    return violations


def _import_group(node: ast.Import | ast.ImportFrom, workspace_root: Path) -> str:
    """Return the import group for a top-level import node."""
    if isinstance(node, ast.Import):
        return _classify_import(node.names[0].name, workspace_root)
    module = node.module or ""
    return _classify_import(module, workspace_root)


GROUP_ORDER = {"stdlib": 0, "third-party": 1, "local": 2}


def _check_import_order(tree: ast.Module, workspace_root: Path) -> list[Violation]:
    """Check that imports are grouped stdlib → third-party → local (F9)."""
    violations: list[Violation] = []
    last_group_rank = -1
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        group = _import_group(node, workspace_root)
        rank = GROUP_ORDER.get(group, 1)
        if rank < last_group_rank:
            violations.append(Violation(
                file="<visitor>", line=node.lineno, scope="<module>",
                rule="F9", detail=f"{group} import after higher-ranked group",
            ))
        last_group_rank = max(last_group_rank, rank)
    return violations


def _check_except_handler(node: ast.ExceptHandler) -> list[Violation]:
    """Check for bare except or except-with-only-pass (F10)."""
    if node.type is None:
        return [Violation(
            file="<visitor>", line=node.lineno, scope="<module>",
            rule="F10", detail="bare except clause; always specify exception type",
        )]
    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
        return [Violation(
            file="<visitor>", line=node.lineno, scope="<module>",
            rule="F10", detail="except clause with only pass; always log or re-raise",
        )]
    return []


class _DisciplineVisitor(ast.NodeVisitor):
    """Visit AST nodes and collect discipline violations."""

    def __init__(self, config: AuditConfig) -> None:
        self.config = config
        self.violations: list[Violation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function violations (F1, F2, F6)."""
        self.violations.extend(_check_function_params(node))
        self.violations.extend(_check_function_body_lines(node))
        self.violations.extend(_check_function_type_hints(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check async function violations (F1, F2, F6)."""
        self.violations.extend(_check_function_params(node))
        self.violations.extend(_check_function_body_lines(node))
        self.violations.extend(_check_function_type_hints(node))
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        """Dispatch non-function nodes to sub-checkers."""
        if isinstance(node, ast.ClassDef):
            self._check_class_node(node)
        elif isinstance(node, ast.Assign):
            self._check_assign_node(node)
        elif isinstance(node, ast.AnnAssign):
            self.violations.extend(_check_annassign_bool(node))
        elif isinstance(node, ast.Call):
            self._check_call_node(node)
        elif isinstance(node, ast.ExceptHandler):
            self.violations.extend(_check_except_handler(node))
        super().generic_visit(node)

    def _check_class_node(self, node: ast.ClassDef) -> None:
        """Check class for max 3 public methods (F3)."""
        public_methods = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and _is_public_method(n.name)
        ]
        if len(public_methods) > MAX_PUBLIC_METHODS:
            detail = f"{len(public_methods)} public methods (max {MAX_PUBLIC_METHODS})"
            self.violations.append(Violation(
                file="<visitor>", line=node.lineno, scope=node.name, rule="F3", detail=detail,
            ))

    def _check_assign_node(self, node: ast.Assign) -> None:
        """Dispatch per-target assign checks (F4, F5)."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.violations.extend(_check_assign_constant(target.id, node))
                self.violations.extend(_check_assign_bool(target.id, node))

    def _check_call_node(self, node: ast.Call) -> None:
        """Check for print() calls (F7)."""
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.violations.append(Violation(
                file="<visitor>", line=node.lineno, scope="<module>",
                rule="F7", detail="print() call found; use logging instead",
            ))


def _audit_file(path: Path, config: AuditConfig) -> list[Violation]:
    """Parse file and audit for violations; return list of Violation objects."""
    ctx = _parse_file(path)
    if ctx is None:
        return []
    visitor = _DisciplineVisitor(config)
    visitor.visit(ctx.tree)
    extra = _check_unused_imports(ctx.tree)
    extra.extend(_check_import_order(ctx.tree, config.workspace_root))
    return visitor.violations + extra


def _audit_directories(config: AuditConfig) -> list[Violation]:
    """Walk directories and audit all Python files; return violations sorted by (file, line)."""
    violations: list[Violation] = []
    for directory in config.directories:
        for py_file in _walk_python_files(directory):
            file_violations = _audit_file(py_file, config)
            for v in file_violations:
                violations.append(Violation(
                    file=str(py_file.relative_to(config.workspace_root)),
                    line=v.line,
                    scope=v.scope,
                    rule=v.rule,
                    detail=v.detail,
                ))
    violations.sort(key=lambda v: (v.file, v.line))
    return violations


def _report_violations(violations: list[Violation]) -> None:
    """Write violations to stdout in spec format: file:line:scope -- rule -- detail."""
    for v in violations:
        sys.stdout.write(f"{v.file}:{v.line}:{v.scope} -- {v.rule} -- {v.detail}\n")


def main() -> None:
    """Main entry point: parse args, audit, report, exit."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    config = _parse_args()
    violations = _audit_directories(config)
    _report_violations(violations)
    exit_code = EXIT_VIOLATIONS if violations else EXIT_CLEAN
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
