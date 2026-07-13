"""Human-controlled review state transitions for vault notes."""

import os
import subprocess
import sys
from pathlib import Path

import yaml

from memory.database import get_db
from memory.indexer import index_vault, parse_frontmatter

VALID_STATES = {"draft", "approved", "rejected", "superseded"}
STATE_DIRS = {
    "draft": "drafts",
    "approved": "approved",
    "rejected": "rejected",
    "superseded": "rejected",
}


def _notes(vault_path: Path, state: str) -> list[Path]:
    directory = vault_path / STATE_DIRS[state]
    return sorted(directory.glob("*.md")) if directory.exists() else []


def list_pending(vault_path: Path) -> list[dict]:
    result = []
    for path in _notes(vault_path, "draft"):
        fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        result.append({"id": path.stem, "title": (fm or {}).get("title", path.stem), "path": str(path), "preview": body[:200]})
    return result


def read_draft(vault_path: Path, draft_id: str) -> str:
    path = vault_path / "drafts" / f"{draft_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"Draft not found: {draft_id}")
    return path.read_text(encoding="utf-8")


def _render(frontmatter: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + body.strip() + "\n"


def transition(vault_path: Path, item_id: str, target: str, superseded_by: str | None = None) -> Path:
    if target not in VALID_STATES - {"draft"}:
        raise ValueError(f"Invalid target state: {target}")
    source = vault_path / "drafts" / f"{item_id}.md" if target != "superseded" else vault_path / "approved" / f"{item_id}.md"
    if not source.exists():
        raise FileNotFoundError(f"Item not found for transition: {item_id}")
    text = source.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    fm = dict(fm or {})
    current = fm.get("status", "draft")
    expected = "approved" if target == "superseded" else "draft"
    if current != expected:
        raise ValueError(f"Cannot transition {current} to {target}")
    fm["status"] = target
    if superseded_by:
        fm["superseded_by"] = superseded_by
    destination_dir = vault_path / STATE_DIRS[target]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    tmp = destination.with_suffix(".md.tmp")
    tmp.write_text(_render(fm, body), encoding="utf-8")
    os.replace(tmp, destination)
    source.unlink()
    source_rel = str(source.relative_to(vault_path))
    destination_rel = str(destination.relative_to(vault_path))
    db = get_db(vault_path)
    db.execute(
        "UPDATE memories SET vault_path=?, status=? WHERE vault_path=? AND archived=0",
        (destination_rel, target, source_rel),
    )
    db.commit()
    index_vault(vault_path, apply=True)
    return destination


def git_commit(vault_path: Path, prefix: str, item_id: str) -> None:
    if not (vault_path / ".git").exists():
        return
    subprocess.run(["git", "add", "--", "."], cwd=vault_path, check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=vault_path)
    if result.returncode:
        subprocess.run(["git", "commit", "-m", f"{prefix}: {item_id}"], cwd=vault_path, check=True)


def git_commit_with_history(
    vault_path: Path,
    affected_paths: list[Path],
    change_id: str,
    memory_id: str,
    change_type: str,
    memory_title: str,
) -> str | None:
    """Commit only affected vault paths; return commit SHA or None.

    Uses git commit --only for isolation. Preserves pre-existing staged changes.
    """
    try:
        # Check if git is available
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=vault_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None  # Not a git repo

        # Stage only affected paths
        for path in affected_paths:
            subprocess.run(
                ["git", "add", "--", str(path)],
                cwd=vault_path,
                check=True,
            )

        # Check for changes in affected paths
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--"] + [str(p) for p in affected_paths],
            cwd=vault_path,
        )

        if result.returncode == 0:
            return None  # No changes to commit

        # Build commit message
        message = f"{change_type}: {memory_title}\n\nMemory-Id: {memory_id}\nMemory-Change-Id: {change_id}"

        # Commit with --only for isolation
        result = subprocess.run(
            ["git", "commit", "--only", "-m", message, "--"] + [str(p) for p in affected_paths],
            cwd=vault_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Git failure is warning, not error
            print(f"warning: git commit failed: {result.stderr}", file=sys.stderr)
            return None

        # Get commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=vault_path,
            capture_output=True,
            text=True,
        )

        return sha_result.stdout.strip() if sha_result.returncode == 0 else None

    except Exception as e:
        print(f"warning: git operation failed: {e}", file=sys.stderr)
        return None
