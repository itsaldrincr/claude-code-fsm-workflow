"""Check Python import resolution and detect unused imports."""

import argparse
import ast
import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

EXIT_CLEAN = 0
EXIT_VIOLATIONS = 1
EXIT_ERROR = 2


@dataclass(frozen=True)
class ImportViolation:
    """A single import violation (unresolvable, unexported, or unused)."""

    file: str
    line: int
    scope: str
    rule: str
    detail: str


@dataclass(frozen=True)
class ParsedImport:
    """A parsed import statement from AST."""

    module: str
    names: list[str]
    line: int
    is_from: bool
    level: int = 0


@dataclass
class DepsConfig:
    """Configuration for dependency checking."""

    directories: list[Path]
    workspace_root: Path


@dataclass(frozen=True)
class ViolationRequest:
    """Parameters for building a single ImportViolation."""

    path: Path
    imp: ParsedImport
    rule: str
    detail: str


@dataclass(frozen=True)
class ResolutionCheckRequest:
    """Parameters for resolution violation check."""

    path: Path
    imports: list[ParsedImport]


@dataclass(frozen=True)
class UnusedCheckRequest:
    """Parameters for unused import violation check."""

    path: Path
    tree: ast.Module
    imports: list[ParsedImport]


def _parse_args() -> DepsConfig:
    """Parse command-line arguments and return DepsConfig."""
    parser = argparse.ArgumentParser(
        description="Check Python import resolution and unused imports"
    )
    parser.add_argument(
        "directories",
        nargs="+",
        type=Path,
        help="Directories to check",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root (default: cwd)",
    )
    args = parser.parse_args()
    return DepsConfig(directories=args.directories, workspace_root=args.workspace_root)


def _walk_python_files(directory: Path) -> Generator[Path, None, None]:
    """Walk directory recursively, yielding Python files."""
    if not directory.is_dir():
        return
    for item in directory.rglob("*.py"):
        if item.is_file():
            yield item


def _extract_plain_imports(tree: ast.Module) -> list[ParsedImport]:
    """Extract ast.Import nodes from module body."""
    imports: list[ParsedImport] = []
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            name_used = alias.asname or alias.name.split(".")[0]
            imports.append(
                ParsedImport(
                    module=alias.name,
                    names=[name_used],
                    line=node.lineno,
                    is_from=False,
                    level=0,
                )
            )
    return imports


def _extract_from_imports(tree: ast.Module) -> list[ParsedImport]:
    """Extract ast.ImportFrom nodes from module body."""
    imports: list[ParsedImport] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        level = node.level or 0
        names = [alias.asname or alias.name for alias in node.names]
        imports.append(
            ParsedImport(
                module=module,
                names=names,
                line=node.lineno,
                is_from=True,
                level=level,
            )
        )
    return imports


def _extract_imports(tree: ast.Module) -> list[ParsedImport]:
    """Extract all imports from AST tree body."""
    return _extract_plain_imports(tree) + _extract_from_imports(tree)


def _resolve_import(parsed: ParsedImport) -> bool:
    """Check if import can be resolved using importlib.util.find_spec."""
    try:
        spec = importlib.util.find_spec(parsed.module)
        return spec is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _check_all_literal(tree: ast.Module, names: list[str]) -> bool | None:
    """Check names against __all__ if it is a list literal; return None if not applicable."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "__all__"):
                continue
            if not isinstance(node.value, ast.List):
                return None
            all_names = [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant)
            ]
            return any(n in all_names for n in names)
    return None


def _static_export_check(module: str, names: list[str]) -> bool | None:
    """Try AST-based __all__ check; return None if inconclusive."""
    spec = importlib.util.find_spec(module)
    if not spec or not spec.has_location:
        return None
    if not spec.origin:
        return None
    source = Path(spec.origin).read_text(encoding="utf-8")
    return _check_all_literal(ast.parse(source), names)


def _check_exported_name(parsed: ParsedImport) -> bool:
    """Check if name is exported from target module (F13)."""
    if not parsed.is_from or parsed.module.startswith("."):
        return True
    try:
        result = _static_export_check(parsed.module, parsed.names)
        if result is not None:
            return result
        mod = importlib.import_module(parsed.module)
        return all(hasattr(mod, n) for n in parsed.names)
    except (ImportError, AttributeError, OSError, SyntaxError) as exc:
        logger.warning("Could not verify export %s from %s: %s", parsed.names[0], parsed.module, exc)
        return True


def _check_unused_imports(tree: ast.Module, imports: list[ParsedImport]) -> list[str]:
    """Return list of imported names that are never used (F14)."""
    imported_names: set[str] = set()
    for imp in imports:
        if imp.module == "__future__":
            continue
        imported_names.update(imp.names)

    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used_names.add(node.id)

    return sorted(imported_names - used_names)


def _make_violation(request: ViolationRequest) -> ImportViolation:
    """Build an ImportViolation for a given import and rule."""
    return ImportViolation(
        file=str(request.path),
        line=request.imp.line,
        scope="module",
        rule=request.rule,
        detail=request.detail,
    )


def _is_relative_import(parsed: ParsedImport) -> bool:
    """Return True if parsed is a relative import."""
    return parsed.level > 0 or parsed.module == "" or parsed.module.startswith(".")


def _check_one_import(path: Path, imp: ParsedImport) -> ImportViolation | None:
    """Check a single import for F11/F13; return violation or None."""
    if not _resolve_import(imp):
        return _make_violation(ViolationRequest(
            path=path, imp=imp, rule="F11",
            detail="Cannot resolve import: %s" % imp.module,
        ))
    if imp.is_from and not _check_exported_name(imp):
        return _make_violation(ViolationRequest(
            path=path, imp=imp, rule="F13",
            detail="Name %s not exported from %s" % (imp.names[0], imp.module),
        ))
    return None


def _is_skippable_import(imp: ParsedImport) -> bool:
    """Return True if import should be skipped for resolution checks."""
    return (
        "*" in imp.names
        or any(n.startswith("__") for n in imp.names)
        or _is_relative_import(imp)
    )


def _check_resolution_violations(request: ResolutionCheckRequest) -> list[ImportViolation]:
    """Check F11 and F13 for each import; return violations."""
    violations: list[ImportViolation] = []
    for imp in request.imports:
        if _is_skippable_import(imp):
            if "*" in imp.names or any(n.startswith("__") for n in imp.names):
                logger.warning("%s:%d: Skipping star or dynamic import", request.path, imp.line)
            continue
        result = _check_one_import(request.path, imp)
        if result is not None:
            violations.append(result)
    return violations


def _check_unused_violations(request: UnusedCheckRequest) -> list[ImportViolation]:
    """Check F14: return a violation for each unused imported name."""
    violations: list[ImportViolation] = []
    for name in _check_unused_imports(request.tree, request.imports):
        for imp in request.imports:
            if name in imp.names:
                v_req = ViolationRequest(
                    path=request.path,
                    imp=imp,
                    rule="F14",
                    detail="Imported name '%s' is unused" % name,
                )
                violations.append(_make_violation(v_req))
                break
    return violations


def _check_file(path: Path, config: DepsConfig) -> list[ImportViolation]:
    """Orchestrate all checks for one file."""
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        logger.warning("Could not parse %s: %s", path, exc)
        return []
    imports = _extract_imports(tree)
    violations = _check_resolution_violations(ResolutionCheckRequest(path=path, imports=imports))
    violations.extend(_check_unused_violations(UnusedCheckRequest(path=path, tree=tree, imports=imports)))
    return violations


def _collect_all_violations(config: DepsConfig) -> list[ImportViolation]:
    """Scan all configured directories and return every violation found."""
    all_violations: list[ImportViolation] = []
    for directory in config.directories:
        for filepath in _walk_python_files(directory):
            all_violations.extend(_check_file(filepath, config))
    all_violations.sort(key=lambda v: (v.file, v.line))
    return all_violations


def main() -> int:
    """Entry point: parse args, check files, report violations."""
    sys.path.insert(0, str(Path.cwd()))
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    config = _parse_args()
    all_violations = _collect_all_violations(config)
    for v in all_violations:
        sys.stdout.write("%s:%d:%s -- %s -- %s\n" % (v.file, v.line, v.scope, v.rule, v.detail))
    return EXIT_VIOLATIONS if all_violations else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
