"""Atomizer script: splits multi-step task files into single-step sub-tasks."""

import argparse
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.fsm_core.frontmatter import TaskFrontmatter, parse_frontmatter

logger = logging.getLogger(__name__)

LETTER_OFFSET = ord("a")
MAX_SUBTASKS = 26
DEFAULT_STATE = "PENDING"
INITIAL_STEP = "0 of 1"
DEFAULT_PADDING_WIDTH = 10


@dataclass
class ProgramStep:
    """Single numbered step from ## Program section."""

    number: int
    text: str


@dataclass
class AtomizeRequest:
    """Input to the atomizer: one or more task file paths."""

    task_paths: list[str]
    map_path: str = "MAP.md"
    is_dry_run: bool = False


@dataclass
class SubtaskConfig:
    """Config for building a single sub-task file."""

    parent_frontmatter: TaskFrontmatter
    step: ProgramStep
    index: int
    total_steps: int
    parent_sections: dict[str, str]
    nonce: str


@dataclass
class MapLineConfig:
    """Config for building a single MAP.md Active Tasks line."""

    prefix: str
    task_filename: str
    padding_width: int
    status: str
    depends_str: str


@dataclass
class MapRewriteConfig:
    """Config for rewriting MAP.md after atomization."""

    map_path: str
    parent_id: str
    subtask_ids: list[str]
    last_subtask_id: str
    parent_files_section: str = ""
    subtask_depends: dict[str, list[str]] | None = None


@dataclass
class DepReplacement:
    """Config for replacing dependency references during MAP rewrite."""

    short_parent: str
    short_last: str


@dataclass
class DependsReplacement:
    """Old and new depends lists for replacing frontmatter depends line."""

    old: list[str]
    new: list[str]


@dataclass
class ParsedTask:
    """Parsed components of a task file."""

    frontmatter: TaskFrontmatter
    steps: list[ProgramStep]
    sections: dict[str, str]


def _find_section_bounds(lines: list[str], header: str) -> tuple[int, int]:
    """Return (start, end) line indices for a ## Section block."""
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start < 0:
        return (-1, -1)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return (start, end)


def parse_sections(content: str) -> dict[str, str]:
    """Extract all ## Section blocks as a dict keyed by section name."""
    lines = content.splitlines()
    headers = [line.strip() for line in lines if re.match(r"^## ", line)]
    result: dict[str, str] = {}
    for header in headers:
        name = header[3:].strip()
        start, end = _find_section_bounds(lines, header)
        if start >= 0:
            result[name] = "\n".join(lines[start:end])
    return result


def _is_fence_line(line: str) -> bool:
    """Return True if line is a fenced code block delimiter."""
    return bool(re.match(r"^\s*```", line))


def _extract_step_text(line: str, next_lines: list[str]) -> str:
    """Gather a step's full text including continuation lines."""
    text_lines = [re.sub(r"^\d+\.\s*", "", line)]
    is_inside_fence = False
    for nl in next_lines:
        if _is_fence_line(nl):
            is_inside_fence = not is_inside_fence
        if not is_inside_fence and re.match(r"^\d+\.", nl.strip()):
            break
        text_lines.append(nl)
    return "\n".join(text_lines).strip()


def parse_program_steps(content: str) -> list[ProgramStep]:
    """Extract numbered steps from ## Program section."""
    sections = parse_sections(content)
    program_body = sections.get("Program", "")
    if not program_body:
        return []
    lines = program_body.splitlines()
    steps: list[ProgramStep] = []
    is_inside_fence = False
    for i, line in enumerate(lines):
        if _is_fence_line(line):
            is_inside_fence = not is_inside_fence
        if is_inside_fence:
            continue
        match = re.match(r"^(\d+)\.", line.strip())
        if not match:
            continue
        num = int(match.group(1))
        text = _extract_step_text(line.strip(), lines[i + 1:])
        steps.append(ProgramStep(number=num, text=text))
    return steps


def generate_nonce() -> str:
    """Call openssl rand -hex 3 to produce a 6-char hex nonce."""
    try:
        result = subprocess.run(
            ["openssl", "rand", "-hex", "3"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("Failed to generate nonce: openssl not available or failed") from exc


def generate_subtask_id(parent_id: str, index: int) -> str:
    """Produce letter-suffix sub-task ID from parent_id and index."""
    suffix = chr(LETTER_OFFSET + index)
    return f"{parent_id}{suffix}"


def _subtask_depends(config: SubtaskConfig) -> list[str]:
    """Compute depends list for a sub-task based on its position."""
    if config.index == 0:
        return list(config.parent_frontmatter.depends)
    prev_id = generate_subtask_id(config.parent_frontmatter.id, config.index - 1)
    return [prev_id]


def _subtask_frontmatter(config: SubtaskConfig) -> str:
    """Render frontmatter block for a sub-task."""
    subtask_id = generate_subtask_id(config.parent_frontmatter.id, config.index)
    depends = _subtask_depends(config)
    depends_str = "[" + ", ".join(depends) + "]" if depends else "[]"
    fm = config.parent_frontmatter
    lines = [
        "---",
        f"id: {subtask_id}",
        f"name: {fm.name}_{chr(LETTER_OFFSET + config.index)}",
        f"state: {DEFAULT_STATE}",
        f"step: {INITIAL_STEP}",
        f"depends: {depends_str}",
        f"wave: {fm.wave}",
        f"dispatch: {fm.dispatch}",
        f"checkpoint: {config.nonce}",
        f"created: {fm.created}",
        f"parent: {fm.id}",
        "---",
    ]
    return "\n".join(lines)


def _copy_sections(sections: dict[str, str], names: list[str]) -> str:
    """Concatenate named sections from dict, returning markdown blocks."""
    parts: list[str] = []
    for name in names:
        if name in sections:
            parts.append(sections[name])
    return "\n\n".join(parts)


def build_subtask(config: SubtaskConfig) -> str:
    """Produce a complete sub-task markdown file string."""
    frontmatter = _subtask_frontmatter(config)
    files_section = config.parent_sections.get("Files", "## Files\n— empty —")
    program_section = f"## Program\n1. {config.step.text}"
    copy_names = ["Registers", "Working Memory", "Acceptance Criteria", "Transition Rules"]
    copied = _copy_sections(config.parent_sections, copy_names)
    parts = [frontmatter, "", files_section, "", program_section]
    if copied:
        parts.append("")
        parts.append(copied)
    return "\n".join(parts) + "\n"


def _write_subtask_file(parent_path: Path, config: SubtaskConfig) -> str:
    """Write one sub-task file to disk, return its path string."""
    subtask_id = generate_subtask_id(config.parent_frontmatter.id, config.index)
    subtask_name = f"{config.parent_frontmatter.name}_{chr(LETTER_OFFSET + config.index)}"
    out_path = parent_path.parent / f"{subtask_id}_{subtask_name}.md"
    out_path.write_text(build_subtask(config), encoding="utf-8")
    logger.info("Created sub-task: %s", out_path)
    return str(out_path)


def _build_subtask_configs(parsed: ParsedTask, total: int) -> list[SubtaskConfig]:
    """Build SubtaskConfig list for all steps of a parsed task."""
    if total > MAX_SUBTASKS:
        raise ValueError(f"Task has {total} steps, exceeding MAX_SUBTASKS={MAX_SUBTASKS}")
    return [
        SubtaskConfig(
            parent_frontmatter=parsed.frontmatter,
            step=step,
            index=i,
            total_steps=total,
            parent_sections=parsed.sections,
            nonce=generate_nonce(),
        )
        for i, step in enumerate(parsed.steps)
    ]


def _parse_task_file(path: Path) -> ParsedTask:
    """Read and parse all components of a task file."""
    content = path.read_text(encoding="utf-8")
    return ParsedTask(
        frontmatter=parse_frontmatter(content),
        steps=parse_program_steps(content),
        sections=parse_sections(content),
    )


def _compute_output_paths(parent_path: Path, parsed: ParsedTask) -> list[Path]:
    """Compute all sub-task output paths without writing them."""
    paths: list[Path] = []
    for i, _ in enumerate(parsed.steps):
        subtask_id = generate_subtask_id(parsed.frontmatter.id, i)
        subtask_name = f"{parsed.frontmatter.name}_{chr(LETTER_OFFSET + i)}"
        paths.append(parent_path.parent / f"{subtask_id}_{subtask_name}.md")
    return paths


def _should_atomize(frontmatter: TaskFrontmatter) -> bool:
    """Check if task should be atomized based on atomize field."""
    return frontmatter.atomize == "required"


def _emit_dry_run_action(task_path: str, parsed: ParsedTask) -> None:
    """Log planned action for a task without executing or writing."""
    if not _should_atomize(parsed.frontmatter):
        action = "PASS-THROUGH"
        reason = f"atomize: {parsed.frontmatter.atomize}"
    elif len(parsed.steps) <= 1:
        action = "PASS-THROUGH"
        reason = "already atomic"
    else:
        action = "ATOMIZE"
        reason = f"{len(parsed.steps)} steps"
    logger.info("%s — %s (%s)", task_path, action, reason)


def atomize_task(task_path: str) -> list[str]:
    """Split a task file into single-step sub-tasks; return created file paths."""
    path = Path(task_path)
    parsed = _parse_task_file(path)
    if not _should_atomize(parsed.frontmatter):
        logger.info("Task %s — skipping (atomize: %s)", parsed.frontmatter.id, parsed.frontmatter.atomize)
        return []
    if len(parsed.steps) <= 1:
        logger.info("Task %s already atomic — skipping", parsed.frontmatter.id)
        return []
    output_paths = _compute_output_paths(path, parsed)
    existing = [p for p in output_paths if p.exists()]
    if existing:
        raise ValueError(f"Sub-task files already exist: {[str(p) for p in existing]}")
    configs = _build_subtask_configs(parsed, len(parsed.steps))
    created = [_write_subtask_file(path, cfg) for cfg in configs]
    path.unlink()
    logger.info("Deleted parent task: %s", task_path)
    return created


def _extract_line_prefix(line: str) -> str:
    """Extract everything before the [ bracket from a MAP.md line."""
    bracket_pos = line.find("[")
    if bracket_pos < 0:
        return line
    return line[:bracket_pos]


def _build_active_task_line(config: MapLineConfig) -> str:
    """Assemble a MAP.md Active Tasks line from config."""
    padding = "." * config.padding_width
    depends_clause = f"  depends: {config.depends_str}" if config.depends_str else ""
    return f"{config.prefix}[{config.task_filename}] {padding}{config.status}{depends_clause}"


@dataclass
class _SubtaskLineInput:
    """Input for building a single sub-task MAP.md line."""

    prefix: str
    subtask_id: str
    subtask_depends: dict[str, list[str]]


def _build_subtask_line(line_input: _SubtaskLineInput) -> str:
    """Build a single MAP.md line for one sub-task."""
    depends_list = line_input.subtask_depends.get(line_input.subtask_id, [])
    depends_str = ", ".join(depends_list) if depends_list else ""
    task_filename = f"{line_input.subtask_id}_*.md"
    line_config = MapLineConfig(
        prefix=line_input.prefix,
        task_filename=task_filename,
        padding_width=DEFAULT_PADDING_WIDTH,
        status="PENDING",
        depends_str=depends_str,
    )
    return _build_active_task_line(line_config)


def _map_replace_parent_entry(config: MapRewriteConfig, map_content: str) -> str:
    """Replace parent task ID bracket entries in MAP.md Active Tasks section."""
    pattern = re.compile(rf"^(.*?)\[{re.escape(config.parent_id)}(?![a-z])_[^\]]*\].*$", re.MULTILINE)
    match = pattern.search(map_content)
    if not match:
        return map_content
    prefix = _extract_line_prefix(match.group(1))
    if not config.subtask_depends:
        config.subtask_depends = {}
    new_lines = [_build_subtask_line(_SubtaskLineInput(prefix, sid, config.subtask_depends)) for sid in config.subtask_ids]
    result = pattern.sub("\n".join(new_lines), map_content)
    if config.parent_files_section:
        result = _map_replace_file_directory(config, result)
    return result


def _extract_directory_from_parent_header(parent_files_section: str) -> str:
    """Extract directory path from parent File Directory header line."""
    lines = parent_files_section.splitlines()
    if not lines:
        return ""
    first_line = lines[0]
    arrow_pos = first_line.find("→")
    if arrow_pos < 0:
        return ""
    after_arrow = first_line[arrow_pos + 1:].strip()
    return after_arrow


def _build_file_directory_block(config: MapRewriteConfig) -> str:
    """Build replacement File Directory blocks for all sub-tasks."""
    directory_path = _extract_directory_from_parent_header(config.parent_files_section)
    content_lines = config.parent_files_section.splitlines()
    content_body = "\n".join(content_lines[1:]) if len(content_lines) > 1 else ""
    blocks: list[str] = []
    for sid in config.subtask_ids:
        header = f"### {sid} → {directory_path}".rstrip()
        block = f"{header}\n{content_body}" if content_body else header
        blocks.append(block)
    return "\n\n".join(blocks)


def _map_replace_file_directory(config: MapRewriteConfig, map_content: str) -> str:
    """Replace the parent's File Directory block with one block per sub-task."""
    pattern = re.compile(
        rf"### {re.escape(config.parent_id)} →[^\n]*\n(.*?)(?=\n+### |\Z)",
        re.DOTALL,
    )
    replacement = _build_file_directory_block(config)
    return pattern.sub(replacement, map_content)


def _replace_dep_in_value(dep_value: str, replacement: DepReplacement) -> str:
    """Replace short_parent with short_last inside a depends value string."""
    return re.sub(rf"\b{re.escape(replacement.short_parent)}\b", replacement.short_last, dep_value)


def _map_rewrite_depends(config: MapRewriteConfig, map_content: str) -> str:
    """Rewrite external dependency references from parent_id to last_subtask_id."""
    short_parent = config.parent_id.split("_")[1] if "_" in config.parent_id else config.parent_id
    short_last = config.last_subtask_id.split("_")[1] if "_" in config.last_subtask_id else config.last_subtask_id
    replacement = DepReplacement(short_parent=short_parent, short_last=short_last)

    def rewrite_line(match: re.Match[str]) -> str:
        dep_value = match.group(1)
        new_value = _replace_dep_in_value(dep_value, replacement)
        return match.group(0).replace(dep_value, new_value)

    return re.sub(r"depends:\s*(\S.*)", rewrite_line, map_content)


def rewrite_map_dependencies(config: MapRewriteConfig) -> str:
    """Read MAP.md, rewrite parent entries and external dep references, return new content."""
    map_path = Path(config.map_path)
    if not map_path.exists():
        logger.warning("MAP.md not found at %s — skipping rewrite", config.map_path)
        return ""
    content = map_path.read_text(encoding="utf-8")
    content = _map_replace_parent_entry(config, content)
    content = _map_rewrite_depends(config, content)
    return content


def _extract_task_id(task_path: str) -> str:
    """Extract task ID (e.g. task_801 or task_801a) from a file path stem."""
    name = Path(task_path).stem
    parts = name.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return name


def _replace_depends_in_content(content: str, replacement: DependsReplacement) -> str:
    """Replace the depends: line in frontmatter with a new list."""
    old_line = f"depends: [{', '.join(replacement.old)}]"
    new_line = f"depends: [{', '.join(replacement.new)}]"
    return content.replace(old_line, new_line, 1)


def _rewrite_parent_depends(task_path: str, rewrites: dict[str, str]) -> None:
    """Update parent task file depends using accumulated parent→last rewrites."""
    if not rewrites:
        return
    path = Path(task_path)
    content = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    if not fm.depends:
        return
    new_depends = [rewrites.get(d, d) for d in fm.depends]
    if new_depends == fm.depends:
        return
    replacement = DependsReplacement(old=fm.depends, new=new_depends)
    path.write_text(_replace_depends_in_content(content, replacement), encoding="utf-8")


def _build_subtask_depends_map(parent_id: str, subtask_ids: list[str]) -> dict[str, list[str]]:
    """Build a map of sub-task ID to its depends list."""
    result: dict[str, list[str]] = {}
    for i, sid in enumerate(subtask_ids):
        if i == 0:
            result[sid] = []
        else:
            result[sid] = [subtask_ids[i - 1]]
    return result


@dataclass
class _MapRewriteInput:
    """Input for rewriting MAP.md after atomizing one parent."""

    parent_id: str
    created: list[str]
    request: AtomizeRequest
    parent_sections: dict[str, str]
    parent_depends: list[str] | None = None


@dataclass
class _ProcessOneTaskInput:
    """Input for processing a single task file for atomization."""

    task_path: str
    request: AtomizeRequest
    rollback: "_RollbackState"
    rewrites: dict[str, str]


def _rewrite_map_for_parent(rewrite_input: _MapRewriteInput) -> None:
    """Rewrite MAP.md after atomizing one parent task."""
    subtask_ids = [_extract_task_id(p) for p in rewrite_input.created]
    last_id = subtask_ids[-1]
    subtask_depends = _build_subtask_depends_map(rewrite_input.parent_id, subtask_ids)
    if subtask_ids and rewrite_input.parent_depends:
        subtask_depends[subtask_ids[0]] = rewrite_input.parent_depends
    cfg = MapRewriteConfig(
        map_path=rewrite_input.request.map_path,
        parent_id=rewrite_input.parent_id,
        subtask_ids=subtask_ids,
        last_subtask_id=last_id,
        parent_files_section=rewrite_input.parent_sections.get("Files", ""),
        subtask_depends=subtask_depends,
    )
    new_content = rewrite_map_dependencies(cfg)
    if new_content:
        Path(rewrite_input.request.map_path).write_text(new_content, encoding="utf-8")
        logger.info("Updated MAP.md for parent %s", rewrite_input.parent_id)


@dataclass
class _RollbackState:
    """State needed to roll back a failed atomization."""

    created_files: list[str]
    parent_backups: dict[str, str]
    map_path: Path
    original_map: str | None


def _process_one_task(input_config: _ProcessOneTaskInput) -> None:
    """Process a single task file for atomization."""
    parsed = _parse_task_file(Path(input_config.task_path))
    input_config.rollback.parent_backups[input_config.task_path] = Path(input_config.task_path).read_text(encoding="utf-8")
    _rewrite_parent_depends(input_config.task_path, input_config.rewrites)
    if not _should_atomize(parsed.frontmatter):
        logger.info("Task %s — skipping (atomize: %s)", parsed.frontmatter.id, parsed.frontmatter.atomize)
        return
    parent_id = _extract_task_id(input_config.task_path)
    parsed = _parse_task_file(Path(input_config.task_path))
    created = atomize_task(input_config.task_path)
    input_config.rollback.created_files.extend(created)
    if created:
        input_config.rewrites[parent_id] = _extract_task_id(created[-1])
        _rewrite_map_for_parent(_MapRewriteInput(parent_id, created, input_config.request, parsed.sections, parsed.frontmatter.depends))


def atomize_tasks(request: AtomizeRequest) -> None:
    """Atomize each task path and update MAP.md for each atomized parent."""
    if request.is_dry_run:
        for task_path in request.task_paths:
            parsed = _parse_task_file(Path(task_path))
            _emit_dry_run_action(task_path, parsed)
        return
    map_path = Path(request.map_path)
    original_map = map_path.read_text(encoding="utf-8") if map_path.exists() else None
    rollback = _RollbackState(created_files=[], parent_backups={}, map_path=map_path, original_map=original_map)
    rewrites: dict[str, str] = {}
    try:
        for task_path in request.task_paths:
            input_config = _ProcessOneTaskInput(task_path=task_path, request=request, rollback=rollback, rewrites=rewrites)
            _process_one_task(input_config)
    except Exception:
        _rollback_atomization(rollback)
        raise


def _rollback_atomization(state: _RollbackState) -> None:
    """Remove created sub-task files, restore parents and MAP.md on failure."""
    logger.error("Atomization failed — rolling back")
    for f in state.created_files:
        path = Path(f)
        if path.exists():
            path.unlink()
            logger.info("Rolled back: %s", f)
    for path_str, content in state.parent_backups.items():
        Path(path_str).write_text(content, encoding="utf-8")
        logger.info("Restored parent: %s", path_str)
    if state.original_map is not None:
        state.map_path.write_text(state.original_map, encoding="utf-8")
        logger.info("Restored original MAP.md")


def main() -> None:
    """CLI entry point: python atomize_task.py [--dry-run] <task_file> [task_file...]"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Atomize multi-step task files into single-step sub-tasks.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files")
    parser.add_argument("task_paths", nargs="+", help="Task file paths to atomize")
    parsed_args = parser.parse_args()
    request = AtomizeRequest(task_paths=parsed_args.task_paths, is_dry_run=parsed_args.dry_run)
    atomize_tasks(request)


if __name__ == "__main__":
    main()
