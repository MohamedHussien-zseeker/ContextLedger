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
