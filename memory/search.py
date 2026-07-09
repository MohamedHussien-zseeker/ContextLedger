"""SQLite FTS5 search."""
from memory.database import get_db
from memory.crud import _row_to_memory


def search(
    vault_path,
    q: str = "",
    tags: list[str] | None = None,
    type_filter: str = "",
    source: str = "",
    limit: int = 10,
    offset: int = 0,
) -> tuple[list, int]:
    db = get_db(vault_path)
    use_fts = bool(q)
    conditions = ["m.archived=0"]
    params = []

    if use_fts:
        conditions.append("m.rowid IN (SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?)")
        params.append(q)

    if tags:
        for tag in tags:
            conditions.append("m.tags LIKE ?")
            params.append(f"%{tag}%")

    if type_filter:
        conditions.append("m.type=?")
        params.append(type_filter)

    if source:
        conditions.append("m.source=?")
        params.append(source)

    where = " AND ".join(conditions)

    count_row = db.execute(f"SELECT COUNT(*) FROM memories m WHERE {where}", params).fetchone()
    total = count_row[0]

    if use_fts:
        rows = db.execute(
            f"""SELECT m.*, bm25(memories_fts) AS score
                FROM memories m
                JOIN memories_fts f ON f.rowid = m.rowid
                WHERE {where}
                ORDER BY score ASC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    else:
        rows = db.execute(
            f"""SELECT m.* FROM memories m
                WHERE {where}
                ORDER BY m.importance DESC, m.accessed_at IS NULL, m.accessed_at DESC, m.created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

    memories = [_row_to_memory(r) for r in rows]

    if use_fts:
        for mem, row in zip(memories, rows):
            mem.score = row["score"]

    if memories:
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ids = [m.id for m in memories]
        placeholders = ",".join("?" for _ in ids)
        db.execute(
            f"UPDATE memories SET access_count=access_count+1, accessed_at=? WHERE id IN ({placeholders})",
            [now] + ids,
        )
        db.commit()

    return memories, total


def related(vault_path, mid: str, limit: int = 5) -> list:
    db = get_db(vault_path)
    rows = db.execute(
        """SELECT m.* FROM memories m
           JOIN memory_relationships r ON r.target_id = m.id
           WHERE r.source_id=? AND m.archived=0
           ORDER BY r.created_at DESC
           LIMIT ?""",
        (mid, limit),
    ).fetchall()
    return [_row_to_memory(r) for r in rows]
