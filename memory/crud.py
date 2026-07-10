import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from memory.database import get_db
from memory.models import MemoryCreate, MemoryResponse, MemoryUpdate


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
        (
            mid,
            m.type,
            m.title,
            m.content,
            m.source,
            m.importance,
            json.dumps(m.tags),
            now,
            now,
            m.vault_path,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()
    return _row_to_memory(row)


def get(vault_path: Path, mid: str) -> Optional[MemoryResponse]:
    db = get_db(vault_path)
    row = db.execute("SELECT * FROM memories WHERE id=? AND archived=0", (mid,)).fetchone()
    if not row:
        return None
    db.execute(
        "UPDATE memories SET access_count=access_count+1, accessed_at=? WHERE id=?",
        (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), mid),
    )
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
    row = db.execute(
        "SELECT * FROM memories WHERE vault_path=? AND archived=0", (vault_path,)
    ).fetchone()
    if row:
        return _row_to_memory(row)
    return None


def upsert_by_vault_path(vault_path_root: Path, vault_path: str, m: MemoryCreate) -> MemoryResponse:
    existing = find_by_vault_path(vault_path_root, vault_path)
    if existing:
        um = MemoryUpdate(
            type=m.type,
            title=m.title,
            content=m.content,
            source=m.source,
            importance=m.importance,
            tags=m.tags,
            vault_path=vault_path,
        )
        return update(vault_path_root, existing.id, um)
    c = m.model_copy(update={"vault_path": vault_path})
    return create(vault_path_root, c)


def replace_relationships(
    vault_path_root: Path, source_id: str, relationships: list[tuple[str, str]]
) -> int:
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
    by_type = dict(
        db.execute("SELECT type, COUNT(*) FROM memories WHERE archived=0 GROUP BY type").fetchall()
    )
    by_source = dict(
        db.execute(
            "SELECT source, COUNT(*) FROM memories WHERE archived=0 GROUP BY source"
        ).fetchall()
    )
    rels = db.execute("SELECT COUNT(*) FROM memory_relationships").fetchone()[0]
    db_size = db.execute(
        "SELECT page_count * page_size FROM pragma_page_count, pragma_page_size"
    ).fetchone()[0]
    return {
        "total_memories": total,
        "by_type": by_type,
        "by_source": by_source,
        "total_relationships": rels,
        "db_size_bytes": db_size,
        "health": "ok",
    }
