"""Process raw sources into linked wiki knowledge notes."""

import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from memory import config
from memory.providers.base import RawSource

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "because",
    "before",
    "being",
    "between",
    "could",
    "every",
    "from",
    "have",
    "into",
    "more",
    "most",
    "notes",
    "only",
    "other",
    "over",
    "same",
    "should",
    "source",
    "their",
    "there",
    "these",
    "this",
    "through",
    "using",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
    "that",
    "they",
    "them",
    "then",
    "than",
    "were",
}
HUBS = {
    "AI Engineering": [
        "agent",
        "agents",
        "automation",
        "workflow",
        "harness",
        "opencode",
        "codex",
        "ai engineering",
    ],
    "LLMs": ["llm", "llms", "model", "models", "claude", "openai", "ollama", "token", "prompt"],
    "RAG": [
        "rag",
        "retrieval",
        "embedding",
        "embeddings",
        "vector",
        "qdrant",
        "semantic",
        "search",
    ],
    "Memory Systems": [
        "memory",
        "obsidian",
        "sqlite",
        "vault",
        "wiki",
        "knowledge",
        "graph",
        "brain",
    ],
    "Prompt Engineering": ["prompt", "prompts", "system prompt", "instruction", "context"],
    "Python": ["python", "fastapi", "sqlite", "script", "pytest"],
    "Business": [
        "business",
        "sales",
        "offer",
        "customer",
        "marketing",
        "pricing",
        "portfolio",
        "commercial",
    ],
    "Cybersecurity": ["security", "cyber", "cybersecurity", "breach", "threat", "auth", "token"],
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "note"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            import yaml

            try:
                data = yaml.safe_load(parts[1]) or {}
                if isinstance(data, dict):
                    return data, parts[2].lstrip()
            except Exception:
                return {}, parts[2].lstrip()
    return {}, text


def scalar(value) -> str:
    text = str(value).replace('"', '\\"')
    if not text or any(ch in text for ch in [":", "#", "[", "]", "{", "}", ","]):
        return f'"{text}"'
    return text


def dump_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for key in sorted(fm):
        value = fm[key]
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(scalar(v) for v in value)}]")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback.replace("-", " ").replace("_", " ").title()


def plain_lines(body: str) -> list[str]:
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("---") or line.startswith("|") or line.startswith("```"):
            continue
        line = re.sub(r"^#+\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        if len(line) >= 30:
            lines.append(line)
    return lines


def keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
    counts = Counter(w for w in words if w not in STOPWORDS and not w.isdigit())
    return [word for word, _count in counts.most_common(limit)]


def choose_hubs(text: str) -> list[str]:
    low = text.lower()
    scored = []
    for hub, terms in HUBS.items():
        score = sum(low.count(term) for term in terms)
        if score:
            scored.append((score, hub))
    scored.sort(reverse=True)
    return [hub for _score, hub in scored[:3]] or ["AI Engineering", "Memory Systems"]


def all_notes(vault_path: Path) -> list[tuple[str, str, str]]:
    notes = []
    skip_dirs = {".obsidian", ".git", "__pycache__", ".trash"}
    for root, dirs, names in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in names:
            if not name.endswith(".md") or name == "_index.md":
                continue
            path = Path(root) / name
            rel = path.relative_to(vault_path).as_posix()
            if rel.startswith(config.RAW_DIR) or rel.startswith(config.GENERATED_DIR):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            _fm, body = parse_frontmatter(text)
            notes.append((rel, title_from_body(body, path.stem), text[:3000]))
    return notes


def related_notes(vault_path: Path, source_text: str, limit: int = 5) -> list[tuple[str, str]]:
    source_keys = set(keywords(source_text, 30))
    scored = []
    for rel, title, text in all_notes(vault_path):
        note_keys = set(keywords(title + "\n" + text, 30))
        score = len(source_keys & note_keys)
        if score:
            scored.append((score, rel, title))
    scored.sort(reverse=True)
    return [(rel, title) for _score, rel, title in scored[:limit]]


def project_link(vault_path: Path, source_text: str) -> tuple[str, str] | None:
    project_dir = vault_path / "01-Projects"
    if not project_dir.exists():
        return None
    source_keys = set(keywords(source_text, 40))
    best = None
    for path in project_dir.rglob("*.md"):
        if path.name == "_index.md":
            continue
        rel = path.relative_to(vault_path).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")[:5000]
        score = len(source_keys & set(keywords(text, 40)))
        if best is None or score > best[0]:
            best = (score, rel, title_from_body(text, path.stem))
    if best and best[0] > 0:
        return best[1], best[2]
    return None


def ensure_hub(vault_path: Path, hub: str, dry_run: bool) -> str:
    slug = slugify(hub)
    rel = f"{config.HUB_DIR}/{slug}.md"
    path = vault_path / rel
    if path.exists():
        return rel
    content = (
        dump_frontmatter(
            {
                "created": now(),
                "status": "active",
                "tags": ["hub", "moc", slug],
            }
        )
        + f"# {hub}\n\n## Generated Knowledge\n\n"
    )
    if not dry_run:
        (vault_path / config.HUB_DIR).mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return rel


def upsert_hub_link(
    vault_path: Path, hub_rel: str, note_rel: str, note_title: str, dry_run: bool
) -> None:
    if dry_run:
        return
    path = vault_path / hub_rel
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    link = f"- [[{note_rel}|{note_title}]]"
    if link in text:
        return
    if "## Generated Knowledge" not in text:
        text = text.rstrip() + "\n\n## Generated Knowledge\n"
    text = text.rstrip() + f"\n{link}\n"
    path.write_text(text, encoding="utf-8")


def process_source(
    vault_path: Path, source_path: Path, force: bool = False, dry_run: bool = False
) -> dict:
    rel_source = source_path.relative_to(vault_path).as_posix()
    text = source_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)
    if fm.get("status") == "processed" and fm.get("processed_note") and not force:
        return {"action": "skip", "source": rel_source, "reason": "already processed"}

    title = title_from_body(body, source_path.stem)
    source_slug = slugify(source_path.stem)
    generated_rel = f"{config.GENERATED_DIR}/{source_slug}.md"
    generated_path = vault_path / generated_rel
    hubs = choose_hubs(title + "\n" + body)
    hub_rels = [ensure_hub(vault_path, hub, dry_run) for hub in hubs]
    rels = related_notes(vault_path, title + "\n" + body)
    project = project_link(vault_path, title + "\n" + body)
    key_terms = keywords(title + "\n" + body, 10)
    lines = plain_lines(body)
    summary = lines[:3] or ["Source captured for later synthesis."]
    insights = lines[3:9] or summary

    generated_fm = {
        "created": fm.get("captured") or fm.get("created") or now(),
        "updated": now(),
        "status": "verified-auto",
        "source": rel_source,
        "source_files": [rel_source],
        "hubs": hubs,
        "tags": sorted({"generated", "llm-wiki", *[slugify(h) for h in hubs], *key_terms[:5]}),
    }
    hub_links = ", ".join(f"[[{rel}|{hub}]]" for rel, hub in zip(hub_rels, hubs))
    related_links = (
        "\n".join(f"- [[{rel}|{related_title}]]" for rel, related_title in rels)
        or "- [[04-Knowledge/_index.md|Knowledge Index]]"
    )
    project_line = (
        f"- [[{project[0]}|{project[1]}]]" if project else "- [[01-Projects/_index.md|Projects]]"
    )
    body_text = dump_frontmatter(generated_fm)
    body_text += f"# {title}\n\n"
    body_text += f"Source: [[{rel_source}|{source_path.stem}]]\n\n"
    body_text += f"Hubs: {hub_links}\n\n"
    body_text += "## Summary\n\n" + "\n".join(f"- {item}" for item in summary) + "\n\n"
    body_text += "## Key Ideas\n\n" + "\n".join(f"- {item}" for item in insights[:6]) + "\n\n"
    if project_line:
        body_text += "## Implementation Relevance\n\n" + project_line + "\n\n"
    body_text += "## Related Notes\n\n" + related_links + "\n\n"
    body_text += "## Source Terms\n\n" + ", ".join(key_terms) + "\n"

    existed_before = generated_path.exists()
    if not dry_run:
        (vault_path / config.GENERATED_DIR).mkdir(parents=True, exist_ok=True)
        generated_path.write_text(body_text, encoding="utf-8")
        for hub_rel, hub in zip(hub_rels, hubs):
            upsert_hub_link(vault_path, hub_rel, generated_rel, title, dry_run=False)
        fm["status"] = "processed"
        fm["processed_at"] = now()
        fm["processed_note"] = generated_rel
        fm["hubs"] = hubs
        source_path.write_text(dump_frontmatter(fm) + body.lstrip(), encoding="utf-8")

    return {
        "action": "update" if existed_before else "write",
        "source": rel_source,
        "note": generated_rel,
        "hubs": hubs,
    }


def process_all(
    vault_path: Path, force: bool = False, dry_run: bool = False, limit: int = 0
) -> list[dict]:
    raw_dir = vault_path / config.RAW_DIR
    results = []
    if not raw_dir.exists():
        return results
    candidates = sorted(p for p in raw_dir.glob("*.md") if p.name != "_index.md")
    if limit:
        candidates = candidates[:limit]
    for source in candidates:
        results.append(process_source(vault_path, source, force=force, dry_run=dry_run))
    return results


def process(
    vault_path: Path, source: RawSource | Path | str, force: bool = False, dry_run: bool = False
) -> dict:
    if isinstance(source, RawSource):
        source_slug = slugify(source.title)
        raw_rel = f"{config.RAW_DIR}/{source_slug}.md"
        raw_path = vault_path / raw_rel
        if not raw_path.exists():
            raw_fm = {
                "captured": source.captured_at,
                "source_type": source.source_type,
                "source_uri": source.source_uri,
                "status": "captured",
                "tags": sorted(source.metadata.get("tags", [])),
            }
            raw_text = dump_frontmatter(raw_fm) + source.content
            if not dry_run:
                (vault_path / config.RAW_DIR).mkdir(parents=True, exist_ok=True)
                raw_path.write_text(raw_text, encoding="utf-8")
        return process_source(vault_path, raw_path, force=force, dry_run=dry_run)
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = vault_path / source_path
    return process_source(vault_path, source_path, force=force, dry_run=dry_run)
