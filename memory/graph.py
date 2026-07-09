"""Graph connectivity analysis for the vault."""
import re
from collections import Counter, defaultdict
from pathlib import Path

WIKILINK_RE = re.compile(r"!?#?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")


def _markdown_files(vault_path: Path) -> dict[str, Path]:
    return {
        p.relative_to(vault_path).as_posix(): p
        for p in vault_path.rglob("*.md")
        if "/.obsidian/" not in str(p)
    }


def _targets(text: str) -> list[str]:
    found = [m.group(1).strip() for m in WIKILINK_RE.finditer(text)]
    found += [m.group(1).strip() for m in MD_LINK_RE.finditer(text)]
    return [t.split("#", 1)[0].strip().replace("\\", "/") for t in found if t.strip()]


def _resolve(target: str, rels: set[str], by_stem: dict[str, list[str]]) -> str | None:
    candidates = [target] if target.endswith(".md") else [f"{target}.md", *by_stem.get(Path(target).stem, [])]
    for candidate in candidates:
        if candidate in rels:
            return candidate
    return None


def health(vault_path: Path) -> dict:
    files = _markdown_files(vault_path)
    rels = set(files)
    by_stem = defaultdict(list)
    for rel in rels:
        by_stem[Path(rel).stem].append(rel)
    adj = {rel: set() for rel in rels}
    inbound = Counter()
    for rel, path in files.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in _targets(text):
            resolved = _resolve(target, rels, by_stem)
            if resolved and resolved != rel:
                adj[rel].add(resolved)
                inbound[resolved] += 1
    linked = {rel for rel, outs in adj.items() if outs or inbound[rel]}
    isolated = [rel for rel in rels if rel not in linked]
    undirected = {rel: set(outs) for rel, outs in adj.items()}
    for src, outs in adj.items():
        for dst in outs:
            undirected[dst].add(src)
    seen = set()
    components = []
    for rel in rels:
        if rel in seen:
            continue
        stack = [rel]
        seen.add(rel)
        comp = []
        while stack:
            current = stack.pop()
            comp.append(current)
            for nxt in undirected[current]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(comp)
    components.sort(key=len, reverse=True)
    generated_isolated = [rel for rel in isolated if rel.startswith("wiki/generated/")]
    total = len(files)
    return {
        "total_notes": total,
        "connected": len(linked),
        "connected_pct": round(len(linked) / total * 100, 1) if total else 0,
        "isolated": len(isolated),
        "isolated_pct": round(len(isolated) / total * 100, 1) if total else 0,
        "components": len(components),
        "largest_component": len(components[0]) if components else 0,
        "largest_component_pct": round(len(components[0]) / total * 100, 1) if components and total else 0,
        "generated_isolated": len(generated_isolated),
        "generated_isolated_files": generated_isolated[:20],
    }
