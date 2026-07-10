"""Index the Obsidian vault into SQLite."""

import os
import re
from collections import defaultdict
from pathlib import Path

from memory.crud import replace_relationships, upsert_by_vault_path
from memory.database import get_db, init_db
from memory.models import MemoryCreate

SKIP_DIRS = {".obsidian", ".git", "__pycache__", ".trash"}
SKIP_FILES = {"_dashboard.md", "_index.md", "_today.md"}
WIKILINK_RE = re.compile(r"!?#?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")

PATH_TYPE_MAP = {
    "01-Projects": "project",
    "02-Prompts": "prompt",
    "03-Code-Snippets": "code",
    "04-Knowledge": "note",
    "05-Logs": "log",
    "06-Templates": "template",
    "00-Inbox": "inbox",
    "wiki": "note",
}


def path_to_type(rel_path: str) -> str:
    for prefix, mtype in PATH_TYPE_MAP.items():
        if rel_path.startswith(prefix):
            return mtype
    return "note"


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml

                fm = yaml.safe_load(parts[1])
                if isinstance(fm, dict):
                    return fm, parts[2].strip()
            except Exception:
                pass
    return None, content.strip()


def extract_title(content: str, frontmatter: dict | None, filename: str) -> str:
    if frontmatter and isinstance(frontmatter, dict):
        raw = frontmatter.get("title")
        if raw and isinstance(raw, str) and raw.strip():
            return raw.strip()
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
    return filename.replace(".md", "").replace("-", " ").replace("_", " ").strip().title()


def extract_tags(frontmatter: dict | None) -> list[str]:
    tags = []
    if not frontmatter:
        return tags
    raw = frontmatter.get("tags", [])
    if isinstance(raw, list):
        tags = [str(t) for t in raw]
    elif isinstance(raw, str):
        tags = [t.strip() for t in raw.split(",")]
    for key in ("project", "hubs"):
        value = frontmatter.get(key)
        if isinstance(value, list):
            tags.extend(str(v) for v in value)
        elif value:
            tags.append(str(value))
    return sorted({t.strip() for t in tags if t and str(t).strip()})


def iter_markdown_files(vault_path: Path, task_dir: str = "00-Inbox/_tasks") -> list[str]:
    files = []
    for root, dirs, names in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if task_dir in root:
            continue
        for name in names:
            if not name.endswith(".md") or name in SKIP_FILES:
                continue
            full = Path(root) / name
            files.append(str(full.relative_to(vault_path)))
    return sorted(files)


def index_file(vault_path: Path, rel_path: str, apply: bool) -> dict:
    full_path = vault_path / rel_path
    content = full_path.read_text(encoding="utf-8", errors="replace")
    fm, _body = parse_frontmatter(content)
    title = extract_title(content, fm, full_path.name)
    tags = extract_tags(fm)
    mtype = path_to_type(rel_path)
    m = MemoryCreate(
        type=mtype,
        title=title,
        content=content,
        source="obsidian",
        importance=2 if mtype == "log" else 3,
        tags=tags,
        vault_path=rel_path,
    )
    if apply:
        result = upsert_by_vault_path(vault_path, rel_path, m)
        is_new = result.created_at == result.updated_at
        return {
            "action": "new" if is_new else "updated",
            "id": result.id,
            "title": title,
            "type": mtype,
        }
    existing = (
        get_db(vault_path)
        .execute("SELECT id FROM memories WHERE vault_path=? AND archived=0", (rel_path,))
        .fetchone()
    )
    return {"action": "dry-run", "existing": existing is not None, "title": title, "type": mtype}


def extract_link_targets(content: str) -> list[str]:
    targets = []
    targets.extend(m.group(1).strip() for m in WIKILINK_RE.finditer(content))
    targets.extend(m.group(1).strip() for m in MD_LINK_RE.finditer(content))
    cleaned = []
    for target in targets:
        target = target.split("#", 1)[0].strip().replace("\\", "/")
        if target:
            cleaned.append(target)
    return cleaned


def rebuild_relationships(vault_path: Path, rel_paths: list[str]) -> int:
    db = get_db(vault_path)
    rows = db.execute(
        "SELECT id, vault_path FROM memories WHERE source='obsidian' AND archived=0 AND vault_path IS NOT NULL"
    ).fetchall()
    path_to_id = {row["vault_path"]: row["id"] for row in rows}
    by_path = {rel: rel for rel in rel_paths}
    by_stem = defaultdict(list)
    for rel in rel_paths:
        by_stem[Path(rel).stem].append(rel)
    total = 0
    for rel in rel_paths:
        source_id = path_to_id.get(rel)
        if not source_id:
            continue
        content = (vault_path / rel).read_text(encoding="utf-8", errors="replace")
        relationships = []
        seen = set()
        for target in extract_link_targets(content):
            resolved = _resolve_target(target, by_path, by_stem)
            if not resolved:
                continue
            target_id = path_to_id.get(resolved)
            if not target_id or target_id == source_id or target_id in seen:
                continue
            seen.add(target_id)
            rel_type = "hub" if resolved.startswith("wiki/hubs/") else "wikilink"
            relationships.append((target_id, rel_type))
        total += replace_relationships(vault_path, source_id, relationships)
    return total


def _resolve_target(
    target: str, by_path: dict[str, str], by_stem: dict[str, list[str]]
) -> str | None:
    candidates = (
        [target]
        if target.endswith(".md")
        else [f"{target}.md", *by_stem.get(Path(target).stem, [])]
    )
    for candidate in candidates:
        if candidate in by_path:
            return candidate
    return None


def archive_missing_vault_paths(vault_path: Path, rel_paths: list[str]) -> int:
    db = get_db(vault_path)
    keep = set(rel_paths)
    rows = db.execute(
        "SELECT id, vault_path FROM memories WHERE source='obsidian' AND archived=0 AND vault_path IS NOT NULL"
    ).fetchall()
    missing = [row["id"] for row in rows if row["vault_path"] not in keep]
    if not missing:
        return 0
    placeholders = ",".join("?" for _ in missing)
    db.execute(f"UPDATE memories SET archived=1 WHERE id IN ({placeholders})", missing)
    db.execute(
        f"DELETE FROM memory_relationships WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
        missing + missing,
    )
    db.commit()
    return len(missing)


def index_vault(vault_path: Path, apply: bool = False) -> dict:
    init_db(vault_path)
    files = iter_markdown_files(vault_path)
    results = []
    for rel in files:
        results.append(index_file(vault_path, rel, apply))
    stats = {"files": len(files), "results": results}
    if apply:
        stats["archived"] = archive_missing_vault_paths(vault_path, files)
        stats["relationships"] = rebuild_relationships(vault_path, files)
        db = get_db(vault_path)
        stats["total_memories"] = db.execute(
            "SELECT COUNT(*) FROM memories WHERE archived=0"
        ).fetchone()[0]
    return stats
