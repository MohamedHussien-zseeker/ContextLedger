"""Deterministic project brief generation from approved notes."""

from datetime import datetime, timezone
from pathlib import Path

from memory.indexer import parse_frontmatter


def assemble_brief(vault_path: Path, project_name: str, project_type: str = "landing-page") -> str:
    records = []
    for path in sorted((vault_path / "approved").glob("*.md")):
        fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if (fm or {}).get("status") != "approved":
            continue
        records.append((fm or {}, body, path.stem))

    def section(category: str) -> str:
        matched = [(fm, body, rid) for fm, body, rid in records if fm.get("hub") == category or fm.get("stack") == category]
        if not matched:
            return "_No approved records yet._"
        return "\n".join(f"- **{fm.get('title', rid)}**: {fm.get('helium_use') or body.splitlines()[0]} `[source: {rid}]`" for fm, body, rid in matched)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""# Helium Project Brief: {project_name}

- **Type:** {project_type}
- **Generated:** {generated}
- **Knowledge policy:** approved records only

## Brand Rules
{section('brand-rules')}

## Core Stack
{section('core-stack')}

## Specialist Stack
Use only with a documented project-specific justification.

{section('specialist-stack')}

## Approved Components
{section('components')}

## Quality Gate
- [ ] Helium brand rules are applied.
- [ ] Core tools are preferred over overlapping references.
- [ ] Every specialist tool has a written justification.
- [ ] Generic and off-brand patterns are rejected.
- [ ] Responsive behavior and WCAG 2.1 AA are verified.
- [ ] Recommendations retain source provenance.
"""


def save_brief(vault_path: Path, project_name: str, project_type: str = "landing-page") -> Path:
    slug = "-".join(project_name.lower().split())
    directory = vault_path / "projects"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.md"
    path.write_text(assemble_brief(vault_path, project_name, project_type), encoding="utf-8")
    return path
