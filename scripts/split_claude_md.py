#!/usr/bin/env python3
"""Split CLAUDE.md into slim template + skill files."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SplitRequest:
    """Request to split CLAUDE.md into template + skill files."""
    source: Path
    output_dir: Path


@dataclass
class SplitResult:
    """Result of splitting CLAUDE.md."""
    slim_template: Path
    skills: list[Path]


@dataclass
class SkillFileSpec:
    """Specification for building a skill file."""
    name: str
    description: str
    color: str
    content: str
    filename: str
    extra_fields: str = ""


@dataclass
class SectionSpec:
    """Specification for extracting a section."""
    lines: list[str]
    start_marker: str
    end_marker: str | None = None


def _find_section_bounds(spec: SectionSpec) -> tuple[int, int]:
    """Find start and end indices for section."""
    start_idx = next((i for i, line in enumerate(spec.lines) if line.startswith(spec.start_marker)), None)
    if start_idx is None:
        return 0, 0
    if not spec.end_marker:
        level = spec.start_marker.count('#')
        end_idx = next((i for i in range(start_idx + 1, len(spec.lines)) if spec.lines[i].startswith('#' * level + ' ')), len(spec.lines))
    else:
        end_idx = next((i for i in range(start_idx + 1, len(spec.lines)) if spec.lines[i].startswith(spec.end_marker)), len(spec.lines))
    return start_idx, end_idx


def _promote_headings(lines: list[str]) -> list[str]:
    """Promote all headings by one level, skipping first."""
    promoted = []
    is_first_heading = True
    is_in_code_block = False
    for line in lines:
        if line.startswith('```'):
            is_in_code_block = not is_in_code_block
            promoted.append(line)
        elif line.startswith('#') and not is_in_code_block:
            if is_first_heading:
                promoted.append(line)
                is_first_heading = False
            else:
                hash_count = len(line) - len(line.lstrip('#'))
                promoted.append('#' * (hash_count - 1) + line[hash_count:])
        else:
            promoted.append(line)
    return promoted


def _extract_section(spec: SectionSpec) -> str:
    """Extract section from content between markers."""
    start_idx, end_idx = _find_section_bounds(spec)
    if start_idx == 0 and end_idx == 0:
        return ""
    return '\n'.join(spec.lines[start_idx:end_idx]).rstrip()


def _extract_and_promote(spec: SectionSpec) -> str:
    """Extract section and promote headings."""
    start_idx, end_idx = _find_section_bounds(spec)
    if start_idx == 0 and end_idx == 0:
        return ""
    extracted_lines = _promote_headings(spec.lines[start_idx:end_idx])
    return '\n'.join(extracted_lines).rstrip()


def _build_skill_file(spec: SkillFileSpec, output_dir: Path) -> Path:
    """Build single skill file with YAML frontmatter."""
    path = output_dir / spec.filename
    extra = f"{spec.extra_fields}\n" if spec.extra_fields else ""
    frontmatter = f"---\nname: {spec.name}\ndescription: {spec.description}\ncolor: {spec.color}\n{extra}---\n\n"
    final_content = frontmatter + spec.content
    if not final_content.endswith('\n'):
        final_content += '\n'
    path.write_text(final_content)
    return path


def _build_roles_skill(lines: list[str], output_dir: Path) -> Path:
    """Build fsm-roles skill file."""
    spec = SectionSpec(lines, '## Roles', '## MAP.md write authority')
    roles = _extract_section(spec)
    spec = SectionSpec(lines, '## Canonical agent names', '## Task File Format')
    canonical = _extract_section(spec)
    content = roles + '\n\n' + canonical
    skill_spec = SkillFileSpec('FSM Roles', 'Canonical roles in the FSM pipeline', 'purple', content, 'fsm-roles.md')
    return _build_skill_file(skill_spec, output_dir)


def _build_task_format_skill(lines: list[str], output_dir: Path) -> Path:
    """Build fsm-task-format skill file."""
    spec = SectionSpec(lines, '## Task File Format', '## MAP.md Format')
    task_format = _extract_and_promote(spec)
    spec = SectionSpec(lines, '## Checkpoint Nonce')
    checkpoint = _extract_and_promote(spec)
    content = task_format + '\n' + checkpoint
    skill_spec = SkillFileSpec('Task File Format', 'Self-contained FSM task file structure', 'blue', content, 'fsm-task-format.md', 'requires_user_confirmation: bool = false')
    return _build_skill_file(skill_spec, output_dir)


def _build_map_format_skill(lines: list[str], output_dir: Path) -> Path:
    """Build fsm-map-format skill file."""
    spec = SectionSpec(lines, '## MAP.md Format', '## Hook enforcement')
    content = _extract_and_promote(spec)
    skill_spec = SkillFileSpec('MAP.md Format', 'Active task tracking and file directory', 'green', content, 'fsm-map-format.md')
    return _build_skill_file(skill_spec, output_dir)


def _build_hook_skill(lines: list[str], output_dir: Path) -> Path:
    """Build fsm-hook-enforcement skill file."""
    spec = SectionSpec(lines, '## Hook enforcement', '## Workflow phases')
    content = _extract_section(spec)
    skill_spec = SkillFileSpec('Hook Enforcement', 'Mechanical enforcement of FSM workflow rules', 'red', content, 'fsm-hook-enforcement.md')
    return _build_skill_file(skill_spec, output_dir)


def _build_workflow_skill(lines: list[str], output_dir: Path) -> Path:
    """Build fsm-workflow-phases skill file."""
    spec = SectionSpec(lines, '## Workflow phases', '## Default behaviour')
    content = _extract_section(spec)
    skill_spec = SkillFileSpec('Workflow Phases', 'FSM pipeline lifecycle', 'orange', content, 'fsm-workflow-phases.md')
    return _build_skill_file(skill_spec, output_dir)


def _build_model_tier_skill(lines: list[str], output_dir: Path) -> Path:
    """Build model-tier-routing skill file."""
    spec = SectionSpec(lines, '## Model Tier Defaults (Max Account)', '## Project Notes')
    content = _extract_section(spec)
    skill_spec = SkillFileSpec('Model Tier Defaults', 'Tier assignments for each FSM agent role', 'yellow', content, 'model-tier-routing.md')
    return _build_skill_file(skill_spec, output_dir)


def _assemble_slim_template(lines: list[str], output_dir: Path) -> Path:
    """Assemble slim template referencing skills."""
    spec = SectionSpec(lines, '# Coding Discipline SOP', '---')
    discipline = _extract_section(spec)
    default_behaviour = _extract_section(SectionSpec(lines, '## Default behaviour', '## Rules'))
    rules = _extract_section(SectionSpec(lines, '## Rules', '## Model Tier Defaults (Max Account)'))
    project_notes = _extract_section(SectionSpec(lines, '## Project Notes'))
    slim_content = (
        f"{discipline}\n\n"
        "---\n\n"
        "## Task Coordination\n\n"
        "This workspace runs a multi-agent FSM pipeline. Roles never overlap.\n\n"
        "## MAP.md write authority\n\n"
        "| Agent | Writes |\n"
        "|---|---|\n"
        "| `task-planner` | Creates/updates MAP.md (atomic with task files) |\n"
        "| `session-closer` | Resets MAP.md at end of session |\n"
        "| Orchestrator | Flips status fields (PENDING → IN_PROGRESS → DONE) |\n"
        "| Everyone else | **Forbidden.** Enforced by `block-map-writes` hook. |\n\n"
        "## Worker context isolation\n\n"
        "Workers receive **only one thing**: their task file path. "
        "The worker-prompt is exact: `Execute task file: <path>. This task file is self-contained. "
        "Read it, follow its Protocol, write code per its Program steps, update Registers with nonce proof, "
        "set state to DONE on success.` Workers do not read MAP.md, CLAUDE.md, specs, or any other project context. "
        "The task file's `## Files` section lists every path needed. Enforced by the `block-worker-reads` hook.\n\n"
        f"{default_behaviour}\n\n"
        f"{rules}\n\n"
        f"{project_notes}\n\n"
        "---\n\n"
        "## Related Skills\n\n"
        "- [fsm-roles](/skills/fsm-roles.md) — Agent roles and canonical names\n"
        "- [fsm-task-format](/skills/fsm-task-format.md) — Task file structure, states, nonce\n"
        "- [fsm-map-format](/skills/fsm-map-format.md) — MAP.md structure and file directory\n"
        "- [fsm-workflow-phases](/skills/fsm-workflow-phases.md) — Pipeline phases and wave gate\n"
        "- [fsm-hook-enforcement](/skills/fsm-hook-enforcement.md) — Hook system\n"
        "- [model-tier-routing](/skills/model-tier-routing.md) — Model tier assignments\n"
    )
    path = output_dir / 'CLAUDE.md'
    path.write_text(slim_content)
    return path


def split(request: SplitRequest) -> SplitResult:
    """Split CLAUDE.md into template and skill files."""
    request.output_dir.mkdir(parents=True, exist_ok=True)
    lines = request.source.read_text().split('\n')
    skills = [
        _build_roles_skill(lines, request.output_dir),
        _build_task_format_skill(lines, request.output_dir),
        _build_map_format_skill(lines, request.output_dir),
        _build_hook_skill(lines, request.output_dir),
        _build_workflow_skill(lines, request.output_dir),
        _build_model_tier_skill(lines, request.output_dir),
    ]
    slim_template = _assemble_slim_template(lines, request.output_dir)
    return SplitResult(slim_template=slim_template, skills=skills)
