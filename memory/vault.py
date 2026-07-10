"""Vault initialization and management."""

from datetime import datetime
from pathlib import Path

from memory import config
from memory.database import init_db

STARTER_STRUCTURE = {
    "00-Inbox": None,
    "04-Knowledge": None,
    "raw": None,
    "wiki": {
        "generated": None,
        "hubs": None,
    },
}


def default_vault_path() -> Path:
    return config.CONFIG_DIR / "vault"


def init_vault(vault_path: Path | None = None) -> Path:
    vault_path = vault_path or default_vault_path()
    if vault_path.exists():
        raise FileExistsError(f"Vault already exists at {vault_path}")
    _create_structure(vault_path)
    _write_index(vault_path)
    init_db(vault_path)
    return vault_path


def _create_structure(base: Path, structure: dict | None = None):
    for name, children in (structure or STARTER_STRUCTURE).items():
        dir_path = base / name
        dir_path.mkdir(parents=True, exist_ok=True)
        if children:
            for child, grandchildren in children.items():
                (dir_path / child).mkdir(parents=True, exist_ok=True)
    (base / "data").mkdir(exist_ok=True)


def _write_index(vault_path: Path):
    content = f"""---
created: {datetime.now().strftime("%Y-%m-%d")}
tags: [vault, index, ai-memory-os]
---

# Memory Vault

## Structure

- `00-Inbox/` — quick captures and bookmarks
- `04-Knowledge/` — reference knowledge
- `raw/` — source materials before processing
- `wiki/generated/` — auto-generated knowledge notes
- `wiki/hubs/` — topic hub MOCs
- `data/` — SQLite database (managed by memory service)
"""
    (vault_path / "_index.md").write_text(content, encoding="utf-8")
