### Task 2: Core Data Layer

**Files:**
- Create: `ai-memory-os/memory/config.py`
- Create: `ai-memory-os/memory/database.py`
- Create: `ai-memory-os/memory/models.py`
- Create: `ai-memory-os/memory/crud.py`
- Create: `tests/test_crud.py`

**Interfaces:**
- Consumes: nothing
- Produces: `database.init_db()`, `models.MemoryCreate`, `models.MemoryResponse`, `crud.create()`, `crud.get()`, `crud.update()`, `crud.archive()`, `crud.upsert_by_vault_path()`, `crud.replace_relationships()`, `crud.get_stats()`

- [ ] **Step 1: Copy and adapt config.py**

Source: `mcp-platform/memory/config.py`

Key change: `DB_PATH` should be relative to the vault, not to the package. Default to `~/.memory/config.toml` for service config, and vault-relative `data/memory.db` for the database.

```python
import os
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_VAULT = Path.home() / ".memory" / "vault"
CONFIG_DIR = Path.home() / ".memory"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# ── Service ───────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 9314
TOKEN_PATH = CONFIG_DIR / "token"

# ── Qdrant (optional) ────────────────────────────────────────────────
QDRANT_HOST = "127.0.0.1"
QDRANT_PORT = 6333
COLLECTION_NAME = "memories"

# ── Embeddings (optional) ────────────────────────────────────────────
OLLAMA_HOST = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768

# ── Vault paths (stable contract) ────────────────────────────────────
RAW_DIR = "raw"
GENERATED_DIR = "wiki/generated"
HUB_DIR = "wiki/hubs"
```

- [ ] **Step 2: Copy database.py**

Source: `mcp-platform/memory/database.py`

Change: `DB_PATH` is no longer imported from config directly. Make `init_db(vault_path: Path)` accept a vault path so the database lives inside the vault.

```python
import sqlite3
import threading
from pathlib import Path

_local = threading.local()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'note',
    title       TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    source      TEXT DEFAULT 'manual',
    importance  INTEGER DEFAULT 1,
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    accessed_at TEXT,
    access_count INTEGER DEFAULT 0,
    archived    INTEGER DEFAULT 0,
    vault_path  TEXT,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS memory_relationships (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES memories(id),
    target_id       TEXT NOT NULL REFERENCES memories(id),
    relationship_type TEXT NOT NULL DEFAULT 'related',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON memory_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON memory_relationships(target_id);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title, content, tags,
    content='memories',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
"""

TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, content, tags)
    VALUES (new.rowid, new.title, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, content, tags)
    VALUES ('delete', old.rowid, old.title, old.content, old.tags);
END;
"""


def get_db(vault_path: Path) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        db_dir = vault_path / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_dir / "memory.db"))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db(vault_path: Path):
    conn = get_db(vault_path)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(TRIGGERS_SQL)
    conn.commit()
```

- [ ] **Step 3: Copy models.py from mcp-platform/memory/models.py** (no changes needed)

- [ ] **Step 4: Copy crud.py from mcp-platform/memory/crud.py**

Change: `get_db()` now takes `vault_path` parameter. Update all functions to accept and pass `vault_path: Path`.

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database import get_db
from models import MemoryCreate, MemoryUpdate, MemoryResponse


def _row_to_memory(row) -> MemoryResponse:
    return MemoryResponse(
        id=row["id"],
        type=row["type"],
        title=row["title"],
        content=row["content"],
        source=row["source"],
        importance=row["importance"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        accessed_at=row["accessed_at"],
        access_count=row["access_count"],
        archived=bool(row["archived"]),
        vault_path=row["vault_path"],
    )


def create(vault_path: Path, m: MemoryCreate) -> MemoryResponse:
    db = get_db(vault_path)
    mid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """INSERT INTO memories (id, type, title, content, source, importance, tags, created_at, updated_at, vault_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (mid, m.type, m.title, m.content, m.source, m.importance, json.dumps(m.tags), now, now, m.vault_path),
    )
    db.commit()
    row = db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
    return _row_to_memory(row)


def get(vault_path: Path, mid: str) -> Optional[MemoryResponse]:
    db = get_db(vault_path)
    row = db.execute("SELECT * FROM memories WHERE id=? AND archived=0", (mid,)).fetchone()
    if not row:
        return None
    db.execute("UPDATE memories SET access_count=access_count+1, accessed_at=? WHERE id=?",
               (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), mid))
    db.commit()
    return _row_to_memory(row)


def update(vault_path: Path, mid: str, m: MemoryUpdate) -> Optional[MemoryResponse]:
    db = get_db(vault_path)
    existing = db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
    if not existing:
        return None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = {}
    for field in ("type", "title", "content", "source", "importance", "vault_path"):
        val = getattr(m, field, None)
        if val is not None:
            fields[field] = val
    if m.tags is not None:
        fields["tags"] = json.dumps(m.tags)
    if not fields:
        return _row_to_memory(existing)
    fields["updated_at"] = now
    set_clause = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE memories SET {set_clause} WHERE id=?", list(fields.values()) + [mid])
    db.commit()
    return _row_to_memory(db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone())


def archive(vault_path: Path, mid: str) -> bool:
    db = get_db(vault_path)
    cur = db.execute(
        "UPDATE memories SET archived=1, updated_at=? WHERE id=? AND archived=0",
        (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), mid),
    )
    db.commit()
    return cur.rowcount > 0


def find_by_vault_path(vault_path_root: Path, vault_path: str) -> Optional[MemoryResponse]:
    db = get_db(vault_path_root)
    row = db.execute("SELECT * FROM memories WHERE vault_path=? AND archived=0", (vault_path,)).fetchone()
    if row:
        return _row_to_memory(row)
    return None


def upsert_by_vault_path(vault_path_root: Path, vault_path: str, m: MemoryCreate) -> MemoryResponse:
    existing = find_by_vault_path(vault_path_root, vault_path)
    if existing:
        um = MemoryUpdate(
            type=m.type, title=m.title, content=m.content, source=m.source,
            importance=m.importance, tags=m.tags, vault_path=vault_path,
        )
        return update(vault_path_root, existing.id, um)
    return create(vault_path_root, m)


def replace_relationships(vault_path_root: Path, source_id: str, relationships: list[tuple[str, str]]) -> int:
    db = get_db(vault_path_root)
    db.execute(
        "DELETE FROM memory_relationships WHERE source_id=? AND relationship_type IN (?, ?)",
        (source_id, "wikilink", "hub"),
    )
    count = 0
    for target_id, relationship_type in relationships:
        if target_id == source_id:
            continue
        db.execute(
            "INSERT INTO memory_relationships (id, source_id, target_id, relationship_type) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), source_id, target_id, relationship_type),
        )
        count += 1
    db.commit()
    return count


def get_stats(vault_path_root: Path) -> dict:
    db = get_db(vault_path_root)
    total = db.execute("SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0]
    by_type = dict(db.execute("SELECT type, COUNT(*) FROM memories WHERE archived=0 GROUP BY type").fetchall())
    by_source = dict(db.execute("SELECT source, COUNT(*) FROM memories WHERE archived=0 GROUP BY source").fetchall())
    rels = db.execute("SELECT COUNT(*) FROM memory_relationships").fetchone()[0]
    db_size = db.execute("SELECT page_count * page_size FROM pragma_page_count, pragma_page_size").fetchone()[0]
    return {
        "total_memories": total,
        "by_type": by_type,
        "by_source": by_source,
        "total_relationships": rels,
        "db_size_bytes": db_size,
        "health": "ok",
    }
```

- [ ] **Step 5: Write test for CRUD operations**

```python
# tests/test_crud.py
import pytest
import tempfile
from pathlib import Path
from memory.database import init_db, get_db
from memory.models import MemoryCreate, MemoryUpdate
from memory.crud import create, get, update, archive, upsert_by_vault_path, get_stats


@pytest.fixture
def vault():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        init_db(path)
        yield path


def test_create_and_get(vault):
    m = create(vault, MemoryCreate(title="Test", content="Hello world", tags=["test"]))
    assert m.title == "Test"
    assert m.id is not None
    fetched = get(vault, m.id)
    assert fetched is not None
    assert fetched.content == "Hello world"


def test_update(vault):
    m = create(vault, MemoryCreate(title="Original"))
    updated = update(vault, m.id, MemoryUpdate(title="Changed"))
    assert updated.title == "Changed"


def test_archive(vault):
    m = create(vault, MemoryCreate(title="To Go"))
    assert archive(vault, m.id) is True
    assert get(vault, m.id) is None


def test_upsert_by_vault_path(vault):
    m1 = upsert_by_vault_path(vault, "test/path.md", MemoryCreate(title="First"))
    assert m1.vault_path == "test/path.md"
    m2 = upsert_by_vault_path(vault, "test/path.md", MemoryCreate(title="Second"))
    assert m2.id == m1.id
    assert m2.title == "Second"


def test_stats(vault):
    create(vault, MemoryCreate(title="A", type="note"))
    create(vault, MemoryCreate(title="B", type="note"))
    create(vault, MemoryCreate(title="C", type="log"))
    stats = get_stats(vault)
    assert stats["total_memories"] == 3
    assert stats["by_type"]["note"] == 2
    assert stats["by_type"]["log"] == 1
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ai-memory-os && python -m pytest tests/test_crud.py -v
```
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: core data layer with SQLite, models, CRUD"
```

---

