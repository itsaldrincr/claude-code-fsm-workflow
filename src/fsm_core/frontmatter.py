"""Task file frontmatter parsing — shared by atomizer and map_reader."""

from dataclasses import dataclass


@dataclass
class TaskFrontmatter:
    """Parsed YAML frontmatter from a task file."""

    id: str
    name: str
    state: str
    step: str
    depends: list[str]
    wave: int
    dispatch: str
    checkpoint: str
    created: str
    parent: str = ""


def _extract_frontmatter_block(content: str) -> str:
    """Extract raw YAML block between first pair of --- delimiters."""
    lines = content.splitlines()
    first = -1
    second = -1
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if first < 0:
                first = i
            else:
                second = i
                break
    if first < 0 or second < 0:
        raise ValueError("Malformed frontmatter: missing --- delimiters")
    return "\n".join(lines[first + 1:second]).strip()


def _parse_depends(raw: str) -> list[str]:
    """Parse depends field from YAML string to list."""
    raw = raw.strip()
    if raw in ("[]", ""):
        return []
    return [v.strip() for v in raw.strip("[]").split(",") if v.strip()]


def _parse_frontmatter_fields(block: str) -> dict[str, str]:
    """Parse YAML block lines into a string dict."""
    result: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        result[key.strip()] = val.strip()
    return result


REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"id", "name", "state", "step", "depends", "wave", "dispatch", "checkpoint", "created"}
)


def parse_frontmatter(content: str) -> TaskFrontmatter:
    """Extract YAML frontmatter between --- delimiters."""
    block = _extract_frontmatter_block(content)
    fields = _parse_frontmatter_fields(block)
    missing = REQUIRED_FIELDS - fields.keys()
    if missing:
        raise ValueError(f"Missing frontmatter fields: {missing}")
    return TaskFrontmatter(
        id=fields["id"],
        name=fields["name"],
        state=fields["state"],
        step=fields["step"],
        depends=_parse_depends(fields["depends"]),
        wave=int(fields["wave"]),
        dispatch=fields["dispatch"],
        checkpoint=fields["checkpoint"],
        created=fields["created"],
        parent=fields.get("parent", ""),
    )
