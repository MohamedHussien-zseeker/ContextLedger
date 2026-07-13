# Git-Backed Memory History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned memory history with Git-backed audit trail to ContextLedger

**Architecture:** History Service owns all memory mutations atomically, recording immutable versions in a new `memory_history` table. CLI, MCP, and REST are thin wrappers that call the service and optionally commit to Git.

**Tech Stack:** SQLite, Python 3.12+, Pydantic, FastAPI, pytest

## Global Constraints

- Python 3.12+ (uses `str | None` union syntax)
- SQLite with WAL mode and foreign keys enabled
- PRAGMA `foreign_keys = ON` on every connection
- Pydantic v2 for request/response models
- Frozen dataclasses for internal service types
- Thread-local database connections via `database.py`
- Atomic file writes via `.tmp` + `os.replace()`
- Git operations use `--only` flag for commit isolation
- CLI exit codes: 0=success, 1=not_found, 2=version_conflict, 3=invalid_transition, 4=validation, 5=deleted
- MCP read-only mode blocks `rollback_memory` from tools/list and rejects direct calls

---

## File Structure

| File | Purpose |
|------|---------|
| `memory/history.py` | **NEW** — HistoryService class with all mutation logic |
| `memory/migrations/v3_history_table.sql` | **NEW** — Schema migration |
| `memory/models.py` | **MODIFY** — Add deleted_at, history models |
| `memory/crud.py` | **MODIFY** — Handle deleted_at column |
| `memory/database.py` | **MODIFY** — Ensure foreign_keys pragma |
| `memory/migrations/runner.py` | **MODIFY** — Atomic migration execution |
| `memory/review.py` | **MODIFY** — Replace git_commit with git_commit_with_history |
| `memory/cli.py` | **MODIFY** — Add history subcommands |
| `memory/mcp/server.py` | **MODIFY** — Add history tools |
| `memory/api/server.py` | **MODIFY** — Add history endpoints |
| `tests/test_history.py` | **NEW** — HistoryService unit tests |
| `tests/test_migrations.py` | **MODIFY** — Add v3 migration tests |

---

### Task 1: Migration v3 — Schema and Backfill

**Files:**
- Create: `memory/migrations/v3_history_table.sql`
- Modify: `memory/migrations/runner.py`
- Test: `tests/test_migrations.py`

**Interfaces:**
- Consumes: existing `memories` table
- Produces: `deleted_at` column on `memories`, new `memory_history` table

- [ ] **Step 1: Create migration file**

Create `memory/migrations/v3_history_table.sql`:

```sql
-- v3: Add history table and soft-delete support

-- Add soft-delete column
ALTER TABLE memories ADD COLUMN deleted_at TEXT DEFAULT NULL;

-- Create history table
CREATE TABLE memory_history (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  change_id TEXT NOT NULL,
  actor_type TEXT NOT NULL CHECK(actor_type IN ('human', 'agent', 'system')),
  initiated_by TEXT,
  executed_by TEXT NOT NULL CHECK(trim(executed_by) <> ''),
  change_type TEXT NOT NULL CHECK(change_type IN ('create', 'update', 'status_change', 'rollback', 'delete')),
  reason TEXT,
  snapshot JSON NOT NULL CHECK(json_valid(snapshot)),
  rolled_back_from_history_id TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(memory_id, version),
  UNIQUE(change_id, memory_id),
  FOREIGN KEY (rolled_back_from_history_id) REFERENCES memory_history(id),
  CHECK (
    (actor_type = 'human' AND initiated_by IS NOT NULL AND trim(initiated_by) <> '')
    OR (actor_type = 'agent')
    OR (actor_type = 'system' AND initiated_by IS NULL)
  )
);

CREATE INDEX idx_history_created_at ON memory_history(created_at);
CREATE INDEX idx_history_executed_by ON memory_history(executed_by);

-- Set deleted_at for archived rows
UPDATE memories SET deleted_at = updated_at WHERE archived = 1 AND deleted_at IS NULL;

-- Backfill all memories as version 1
INSERT INTO memory_history (id, memory_id, version, change_id, actor_type, initiated_by, executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at)
SELECT
  lower(hex(randomblob(16))),
  id,
  1,
  lower(hex(randomblob(16))),
  'system',
  NULL,
  'history-v2-migration',
  CASE WHEN archived = 1 THEN 'delete' ELSE 'create' END,
  'Baseline created during v2 history migration',
  json_object(
    'schema_version', 1,
    'title', title,
    'content', content,
    'status', status,
    'tags', json(CASE WHEN json_valid(tags) THEN tags ELSE '[]' END),
    'importance', importance,
    'vault_path', vault_path,
    'deleted', json(CASE WHEN archived = 1 THEN 'true' ELSE 'false' END)
  ),
  NULL,
  strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM memories;
```

- [ ] **Step 2: Fix migration runner for atomic execution**

Modify `memory/migrations/runner.py` to use `BEGIN IMMEDIATE` inside the script:

```python
def run_migrations(db: sqlite3.Connection):
    """Run pending migrations using the provided connection.
    
    The caller owns the connection (typically from init_db()).
    Each migration runs in a single transactional script with the marker.
    """
    from glob import glob
    import os
    
    migrations_dir = os.path.dirname(__file__)
    pattern = os.path.join(migrations_dir, "v*.sql")
    
    # Get applied versions
    try:
        rows = db.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {row[0] for row in rows}
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
        """)
        applied = set()
    
    for migration_file in sorted(glob(pattern)):
        basename = os.path.basename(migration_file)
        version = os.path.splitext(basename)[0]
        
        if version in applied:
            continue
        
        with open(migration_file, 'r') as f:
            sql = f.read()
        
        version_sql = version.replace("'", "''")
        script = f"""
BEGIN IMMEDIATE;
{sql}
INSERT INTO schema_migrations (version)
VALUES ('{version_sql}');
COMMIT;
"""
        
        try:
            db.executescript(script)
        except Exception:
            db.rollback()
            raise
```

- [ ] **Step 3: Run existing migration tests to verify no regression**

Run: `pytest tests/test_migrations.py -v`
Expected: All existing tests pass

- [ ] **Step 4: Write v3 migration tests**

Add to `tests/test_migrations.py`:

```python
def test_v3_fresh_database(tmp_path):
    """Create new DB, run all migrations, verify schema."""
    from memory.database import init_db
    
    db_path = str(tmp_path / "test.db")
    db = init_db(db_path)
    
    # Verify deleted_at column exists
    cols = [row[1] for row in db.execute("PRAGMA table_info(memories)").fetchall()]
    assert "deleted_at" in cols
    
    # Verify memory_history table exists
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "memory_history" in tables
    
    db.close()


def test_v3_upgrade_with_active_and_archived(tmp_path):
    """Insert active + archived memories, run v3, verify backfill."""
    from memory.database import init_db
    
    db_path = str(tmp_path / "test.db")
    db = init_db(db_path)
    
    # Insert test memories
    db.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, archived, updated_at)
        VALUES ('active-1', 'note', 'Active Note', 'Content', 'draft', 1, 0, '2026-07-13T00:00:00Z')
    """)
    db.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, archived, updated_at)
        VALUES ('archived-1', 'note', 'Archived Note', 'Content', 'draft', 1, 1, '2026-07-12T00:00:00Z')
    """)
    db.commit()
    
    # Run v3 migration
    from memory.migrations.runner import run_migrations
    run_migrations(db)
    
    # Verify backfill
    history = db.execute("SELECT * FROM memory_history ORDER BY memory_id").fetchall()
    assert len(history) == 2
    
    # Active memory should have change_type='create'
    active_history = [h for h in history if h[1] == 'active-1'][0]
    assert active_history[6] == 'create'  # change_type column
    
    # Archived memory should have change_type='delete'
    archived_history = [h for h in history if h[1] == 'archived-1'][0]
    assert archived_history[6] == 'delete'
    
    # Verify deleted_at set for archived
    archived_row = db.execute("SELECT deleted_at FROM memories WHERE id='archived-1'").fetchone()
    assert archived_row[0] is not None
    
    db.close()


def test_v3_json_tags_are_arrays(tmp_path):
    """Verify tags column produces JSON array, not escaped string."""
    from memory.database import init_db
    
    db_path = str(tmp_path / "test.db")
    db = init_db(db_path)
    
    # Insert memory with tags
    db.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, tags)
        VALUES ('tags-1', 'note', 'Tagged', 'Content', 'draft', 1, '["tag1", "tag2"]')
    """)
    db.commit()
    
    from memory.migrations.runner import run_migrations
    run_migrations(db)
    
    # Verify snapshot tags is JSON array
    import json
    snapshot = db.execute("SELECT snapshot FROM memory_history WHERE memory_id='tags-1'").fetchone()
    data = json.loads(snapshot[0])
    assert isinstance(data["tags"], list)
    assert data["tags"] == ["tag1", "tag2"]
    
    db.close()


def test_v3_idempotent(tmp_path):
    """Run migration twice, no errors, no duplicate history."""
    from memory.database import init_db
    from memory.migrations.runner import run_migrations
    
    db_path = str(tmp_path / "test.db")
    db = init_db(db_path)
    
    db.execute("""
        INSERT INTO memories (id, type, title, content, status, importance)
        VALUES ('idem-1', 'note', 'Test', 'Content', 'draft', 1)
    """)
    db.commit()
    
    # Run twice
    run_migrations(db)
    count1 = db.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]
    
    run_migrations(db)
    count2 = db.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]
    
    assert count1 == count2 == 1
    
    db.close()
```

- [ ] **Step 5: Run v3 migration tests**

Run: `pytest tests/test_migrations.py -v`
Expected: All tests pass including new v3 tests

- [ ] **Step 6: Commit**

```bash
git add memory/migrations/v3_history_table.sql memory/migrations/runner.py tests/test_migrations.py
git commit -m "feat: add v3 history migration with atomic runner"
```

---

### Task 2: History Service Core

**Files:**
- Create: `memory/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `memory.database.get_db()`, `memory.models.MemoryResponse`
- Produces: `HistoryService` class, `HistoryEntry`, `FieldDiff`, `MutationResult` dataclasses

- [ ] **Step 1: Create history.py with dataclasses**

Create `memory/history.py`:

```python
"""Memory history service for versioned tracking."""

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class HistoryError(Exception):
    """Base exception for history operations."""


class MemoryNotFoundError(HistoryError):
    """Memory does not exist."""


class VersionConflictError(HistoryError):
    """Optimistic concurrency conflict."""
    
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"Expected version {expected}, current version is {current}")


class InvalidTransitionError(HistoryError):
    """Status transition not allowed."""


class DeletedMemoryError(HistoryError):
    """Cannot modify a deleted memory."""


class ValidationError(HistoryError):
    """Invalid snapshot or actor configuration."""


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    memory_id: str
    version: int
    change_id: str
    actor_type: str
    initiated_by: str | None
    executed_by: str
    change_type: str
    reason: str | None
    snapshot: dict
    rolled_back_from_history_id: str | None
    created_at: str


@dataclass(frozen=True)
class FieldDiff:
    field: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True)
class MutationResult:
    entry: HistoryEntry
    changed: bool


# Status transition rules
VALID_TRANSITIONS = {
    "draft": {"approved", "rejected"},
    "approved": {"superseded", "rejected"},
    "rejected": {"draft"},
    "superseded": set(),
}

# Required snapshot keys
SNAPSHOT_KEYS = {"schema_version", "title", "content", "status", "tags", "importance", "vault_path", "deleted"}


def _generate_id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _validate_snapshot(snapshot: dict) -> None:
    """Validate snapshot has required keys and correct types."""
    missing = SNAPSHOT_KEYS - set(snapshot.keys())
    if missing:
        raise ValidationError(f"Snapshot missing required keys: {missing}")
    
    if snapshot.get("schema_version") != 1:
        raise ValidationError("snapshot.schema_version must be 1")
    
    if not isinstance(snapshot.get("tags"), list):
        raise ValidationError("snapshot.tags must be a list")
    
    if not isinstance(snapshot.get("importance"), int):
        raise ValidationError("snapshot.importance must be an integer")
    
    if snapshot.get("deleted") not in (True, False):
        raise ValidationError("snapshot.deleted must be a boolean")


def _validate_actor(actor_type: str, initiated_by: str | None) -> None:
    """Validate actor configuration."""
    if actor_type not in ("human", "agent", "system"):
        raise ValidationError(f"Invalid actor_type: {actor_type}")
    
    if actor_type == "human" and (not initiated_by or not initiated_by.strip()):
        raise ValidationError("human actor_type requires initiated_by")
    
    if actor_type == "system" and initiated_by is not None:
        raise ValidationError("system actor_type must have initiated_by=None")


def _canonicalize_tags(tags: list) -> list:
    """Sort tags for comparison."""
    return sorted(tags)


def _snapshots_differ(a: dict, b: dict) -> bool:
    """Compare two snapshots for meaningful differences."""
    for key in SNAPSHOT_KEYS:
        val_a = a.get(key)
        val_b = b.get(key)
        
        if key == "tags":
            val_a = _canonicalize_tags(val_a) if val_a else []
            val_b = _canonicalize_tags(val_b) if val_b else []
        
        if val_a != val_b:
            return True
    return False
```

- [ ] **Step 2: Add HistoryService class**

Append to `memory/history.py`:

```python
class HistoryService:
    """Service for versioned memory history tracking.
    
    All mutations go through this service. It owns the complete
    transaction: update memories + insert memory_history atomically.
    """
    
    def __init__(self, db: sqlite3.Connection):
        self.db = db
    
    def create_memory(
        self,
        memory_id: str,
        snapshot: dict,
        actor_type: str,
        executed_by: str,
        initiated_by: str | None = None,
        change_id: str | None = None,
        reason: str | None = None,
    ) -> MutationResult:
        """Create new memory + initial history entry."""
        _validate_snapshot(snapshot)
        _validate_actor(actor_type, initiated_by)
        
        if not executed_by or not executed_by.strip():
            raise ValidationError("executed_by is required")
        
        change_id = change_id or _generate_id()
        
        return self._execute_atomic(
            memory_id=memory_id,
            change_id=change_id,
            change_type="create",
            snapshot=snapshot,
            actor_type=actor_type,
            executed_by=executed_by,
            initiated_by=initiated_by,
            reason=reason,
        )
    
    def update_memory(
        self,
        memory_id: str,
        snapshot: dict,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str | None = None,
        change_id: str | None = None,
        reason: str | None = None,
    ) -> MutationResult:
        """Update memory fields. Returns MutationResult with changed=False if no-op."""
        _validate_snapshot(snapshot)
        _validate_actor(actor_type, initiated_by)
        
        if not executed_by or not executed_by.strip():
            raise ValidationError("executed_by is required")
        
        change_id = change_id or _generate_id()
        
        return self._execute_atomic(
            memory_id=memory_id,
            change_id=change_id,
            change_type="update",
            snapshot=snapshot,
            actor_type=actor_type,
            executed_by=executed_by,
            expected_version=expected_version,
            initiated_by=initiated_by,
            reason=reason,
        )
    
    def change_status(
        self,
        memory_id: str,
        new_status: str,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str | None = None,
        change_id: str | None = None,
        reason: str | None = None,
    ) -> MutationResult:
        """Validate transition rules, then update status."""
        _validate_actor(actor_type, initiated_by)
        
        if not executed_by or not executed_by.strip():
            raise ValidationError("executed_by is required")
        
        # Load current memory to validate transition
        current = self.db.execute(
            "SELECT status, deleted_at FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()
        
        if not current:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        
        if current[1] is not None:
            raise DeletedMemoryError(f"Memory {memory_id} is deleted")
        
        current_status = current[0]
        if new_status not in VALID_TRANSITIONS.get(current_status, set()):
            raise InvalidTransitionError(
                f"Cannot transition from {current_status} to {new_status}"
            )
        
        # Build snapshot with new status
        # We need to load the full current memory to build snapshot
        row = self.db.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()
        
        snapshot = {
            "schema_version": 1,
            "title": row[2],  # title
            "content": row[3],  # content
            "status": new_status,
            "tags": json.loads(row[7]) if row[7] else [],  # tags
            "importance": row[6],  # importance
            "vault_path": row[13],  # vault_path
            "deleted": False,
        }
        
        change_id = change_id or _generate_id()
        
        return self._execute_atomic(
            memory_id=memory_id,
            change_id=change_id,
            change_type="status_change",
            snapshot=snapshot,
            actor_type=actor_type,
            executed_by=executed_by,
            expected_version=expected_version,
            initiated_by=initiated_by,
            reason=reason,
        )
    
    def delete_memory(
        self,
        memory_id: str,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str | None = None,
        change_id: str | None = None,
        reason: str | None = None,
    ) -> MutationResult:
        """Soft-delete: set deleted_at, append tombstone snapshot."""
        _validate_actor(actor_type, initiated_by)
        
        if not executed_by or not executed_by.strip():
            raise ValidationError("executed_by is required")
        
        # Load current memory
        row = self.db.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()
        
        if not row:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        
        if row[15] is not None:  # deleted_at column
            raise DeletedMemoryError(f"Memory {memory_id} is already deleted")
        
        # Build tombstone snapshot
        snapshot = {
            "schema_version": 1,
            "title": row[2],
            "content": row[3],
            "status": row[8] if len(row) > 8 else "draft",  # status
            "tags": json.loads(row[7]) if row[7] else [],
            "importance": row[6],
            "vault_path": row[13],
            "deleted": True,
        }
        
        change_id = change_id or _generate_id()
        
        return self._execute_atomic(
            memory_id=memory_id,
            change_id=change_id,
            change_type="delete",
            snapshot=snapshot,
            actor_type=actor_type,
            executed_by=executed_by,
            expected_version=expected_version,
            initiated_by=initiated_by,
            reason=reason,
        )
    
    def rollback(
        self,
        memory_id: str,
        target_version: int,
        expected_version: int,
        actor_type: str,
        executed_by: str,
        initiated_by: str | None = None,
        change_id: str | None = None,
        reason: str | None = None,
    ) -> MutationResult:
        """Restore from target. Non-deleted → restore. Tombstone → soft-delete."""
        _validate_actor(actor_type, initiated_by)
        
        if not executed_by or not executed_by.strip():
            raise ValidationError("executed_by is required")
        
        # Load target snapshot
        target = self.db.execute(
            "SELECT id, snapshot FROM memory_history WHERE memory_id = ? AND version = ?",
            (memory_id, target_version)
        ).fetchone()
        
        if not target:
            raise MemoryNotFoundError(
                f"Version {target_version} not found for memory {memory_id}"
            )
        
        target_history_id = target[0]
        target_snapshot = json.loads(target[1])
        
        # Check if memory exists
        memory = self.db.execute(
            "SELECT id, deleted_at FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()
        
        if not memory:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        
        # Build rollback snapshot
        snapshot = {
            "schema_version": 1,
            "title": target_snapshot["title"],
            "content": target_snapshot["content"],
            "status": target_snapshot["status"],
            "tags": target_snapshot["tags"],
            "importance": target_snapshot["importance"],
            "vault_path": target_snapshot["vault_path"],
            "deleted": target_snapshot.get("deleted", False),
        }
        
        change_id = change_id or _generate_id()
        
        return self._execute_atomic(
            memory_id=memory_id,
            change_id=change_id,
            change_type="rollback",
            snapshot=snapshot,
            actor_type=actor_type,
            executed_by=executed_by,
            expected_version=expected_version,
            initiated_by=initiated_by,
            reason=reason,
            rolled_back_from_history_id=target_history_id,
        )
    
    def get_log(
        self,
        memory_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HistoryEntry]:
        """Query history with optional memory_id filter."""
        if memory_id:
            rows = self.db.execute(
                """SELECT id, memory_id, version, change_id, actor_type, initiated_by,
                          executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at
                   FROM memory_history
                   WHERE memory_id = ?
                   ORDER BY created_at DESC, id DESC
                   LIMIT ? OFFSET ?""",
                (memory_id, limit, offset),
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT id, memory_id, version, change_id, actor_type, initiated_by,
                          executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at
                   FROM memory_history
                   ORDER BY created_at DESC, id DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        
        return [
            HistoryEntry(
                id=row[0],
                memory_id=row[1],
                version=row[2],
                change_id=row[3],
                actor_type=row[4],
                initiated_by=row[5],
                executed_by=row[6],
                change_type=row[7],
                reason=row[8],
                snapshot=json.loads(row[9]),
                rolled_back_from_history_id=row[10],
                created_at=row[11],
            )
            for row in rows
        ]
    
    def diff_versions(
        self,
        memory_id: str,
        version_a: int,
        version_b: int,
    ) -> list[FieldDiff]:
        """Compare two snapshots."""
        row_a = self.db.execute(
            "SELECT snapshot FROM memory_history WHERE memory_id = ? AND version = ?",
            (memory_id, version_a),
        ).fetchone()
        
        row_b = self.db.execute(
            "SELECT snapshot FROM memory_history WHERE memory_id = ? AND version = ?",
            (memory_id, version_b),
        ).fetchone()
        
        if not row_a:
            raise MemoryNotFoundError(f"Version {version_a} not found for memory {memory_id}")
        if not row_b:
            raise MemoryNotFoundError(f"Version {version_b} not found for memory {memory_id}")
        
        snap_a = json.loads(row_a[0])
        snap_b = json.loads(row_b[0])
        
        diffs = []
        for key in sorted(SNAPSHOT_KEYS):
            val_a = snap_a.get(key)
            val_b = snap_b.get(key)
            
            if key == "tags":
                val_a = _canonicalize_tags(val_a) if val_a else []
                val_b = _canonicalize_tags(val_b) if val_b else []
            
            if val_a != val_b:
                diffs.append(FieldDiff(field=key, old_value=val_a, new_value=val_b))
        
        return diffs
    
    def _execute_atomic(
        self,
        memory_id: str,
        change_id: str,
        change_type: str,
        snapshot: dict,
        actor_type: str,
        executed_by: str,
        expected_version: int | None = None,
        initiated_by: str | None = None,
        reason: str | None = None,
        rolled_back_from_history_id: str | None = None,
    ) -> MutationResult:
        """Internal: BEGIN IMMEDIATE, idempotency check, version allocation,
        field comparison, memory update, history insert, COMMIT.
        Rolls back on any exception."""
        try:
            self.db.execute("BEGIN IMMEDIATE")
            
            # Idempotency check
            existing = self.db.execute(
                "SELECT id, memory_id, version, change_id, actor_type, initiated_by, "
                "executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at "
                "FROM memory_history WHERE change_id = ? AND memory_id = ?",
                (change_id, memory_id),
            ).fetchone()
            
            if existing:
                entry = HistoryEntry(
                    id=existing[0],
                    memory_id=existing[1],
                    version=existing[2],
                    change_id=existing[3],
                    actor_type=existing[4],
                    initiated_by=existing[5],
                    executed_by=existing[6],
                    change_type=existing[7],
                    reason=existing[8],
                    snapshot=json.loads(existing[9]),
                    rolled_back_from_history_id=existing[10],
                    created_at=existing[11],
                )
                self.db.commit()
                return MutationResult(entry=entry, changed=False)
            
            # Get current version
            row = self.db.execute(
                "SELECT MAX(version) FROM memory_history WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            current_version = row[0] or 0
            
            # Optimistic concurrency check
            if expected_version is not None and current_version != expected_version:
                self.db.commit()
                raise VersionConflictError(expected_version, current_version)
            
            # Check for no-op (compare with current snapshot)
            if change_type in ("update", "status_change"):
                current_row = self.db.execute(
                    "SELECT snapshot FROM memory_history WHERE memory_id = ? AND version = ?",
                    (memory_id, current_version),
                ).fetchone()
                if current_row:
                    current_snapshot = json.loads(current_row[0])
                    if not _snapshots_differ(current_snapshot, snapshot):
                        # No-op: return existing entry
                        entry_row = self.db.execute(
                            "SELECT id, memory_id, version, change_id, actor_type, initiated_by, "
                            "executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at "
                            "FROM memory_history WHERE memory_id = ? AND version = ?",
                            (memory_id, current_version),
                        ).fetchone()
                        entry = HistoryEntry(
                            id=entry_row[0],
                            memory_id=entry_row[1],
                            version=entry_row[2],
                            change_id=entry_row[3],
                            actor_type=entry_row[4],
                            initiated_by=entry_row[5],
                            executed_by=entry_row[6],
                            change_type=entry_row[7],
                            reason=entry_row[8],
                            snapshot=json.loads(entry_row[9]),
                            rolled_back_from_history_id=entry_row[10],
                            created_at=entry_row[11],
                        )
                        self.db.commit()
                        return MutationResult(entry=entry, changed=False)
            
            # Allocate new version
            new_version = current_version + 1
            
            # Insert history entry
            history_id = _generate_id()
            self.db.execute(
                """INSERT INTO memory_history 
                   (id, memory_id, version, change_id, actor_type, initiated_by, executed_by,
                    change_type, reason, snapshot, rolled_back_from_history_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    history_id,
                    memory_id,
                    new_version,
                    change_id,
                    actor_type,
                    initiated_by,
                    executed_by,
                    change_type,
                    reason,
                    json.dumps(snapshot),
                    rolled_back_from_history_id,
                    _now(),
                ),
            )
            
            # Update memories table
            deleted_at = _now() if snapshot.get("deleted") else None
            archived = 1 if snapshot.get("deleted") else 0
            
            if change_type == "create":
                # Insert new memory
                self.db.execute(
                    """INSERT INTO memories (id, type, title, content, status, importance, tags,
                       vault_path, archived, deleted_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        memory_id,
                        "note",
                        snapshot["title"],
                        snapshot["content"],
                        snapshot["status"],
                        snapshot["importance"],
                        json.dumps(snapshot["tags"]),
                        snapshot["vault_path"],
                        archived,
                        deleted_at,
                        _now(),
                        _now(),
                    ),
                )
            else:
                # Update existing memory
                self.db.execute(
                    """UPDATE memories 
                       SET title = ?, content = ?, status = ?, importance = ?, tags = ?,
                           vault_path = ?, archived = ?, deleted_at = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        snapshot["title"],
                        snapshot["content"],
                        snapshot["status"],
                        snapshot["importance"],
                        json.dumps(snapshot["tags"]),
                        snapshot["vault_path"],
                        archived,
                        deleted_at,
                        _now(),
                        memory_id,
                    ),
                )
            
            self.db.commit()
            
            entry = HistoryEntry(
                id=history_id,
                memory_id=memory_id,
                version=new_version,
                change_id=change_id,
                actor_type=actor_type,
                initiated_by=initiated_by,
                executed_by=executed_by,
                change_type=change_type,
                reason=reason,
                snapshot=snapshot,
                rolled_back_from_history_id=rolled_back_from_history_id,
                created_at=_now(),
            )
            
            return MutationResult(entry=entry, changed=True)
            
        except Exception:
            self.db.rollback()
            raise
```

- [ ] **Step 3: Write unit tests for HistoryService**

Create `tests/test_history.py`:

```python
"""Tests for memory history service."""

import json
import sqlite3
import threading
import time
import pytest
from memory.database import init_db
from memory.history import (
    HistoryService,
    HistoryEntry,
    MutationResult,
    MemoryNotFoundError,
    VersionConflictError,
    InvalidTransitionError,
    DeletedMemoryError,
    ValidationError,
)


@pytest.fixture
def db():
    """Create a fresh test database."""
    import tempfile
    import os
    
    # Reset thread-local connection
    from memory.database import _local
    _local.conn = None
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        conn = init_db(db_path)
        yield conn
        conn.close()
        _local.conn = None


@pytest.fixture
def service(db):
    """Create HistoryService with test database."""
    return HistoryService(db)


def _make_snapshot(title="Test", status="draft", tags=None, importance=1, deleted=False):
    """Create a valid snapshot for testing."""
    return {
        "schema_version": 1,
        "title": title,
        "content": f"# {title}\n\nContent here.",
        "status": status,
        "tags": tags or [],
        "importance": importance,
        "vault_path": f"test/{title.lower()}.md",
        "deleted": deleted,
    }


class TestCreateMemory:
    def test_create_success(self, service):
        snapshot = _make_snapshot()
        result = service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert isinstance(result, MutationResult)
        assert result.changed is True
        assert result.entry.memory_id == "mem-1"
        assert result.entry.version == 1
        assert result.entry.change_type == "create"
        assert result.entry.snapshot["title"] == "Test"
    
    def test_create_rejects_existing(self, service):
        snapshot = _make_snapshot()
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        with pytest.raises(sqlite3.IntegrityError):
            service.create_memory(
                memory_id="mem-1",
                snapshot=snapshot,
                actor_type="human",
                executed_by="zserverai",
                initiated_by="zserverai",
            )
    
    def test_create_validates_snapshot(self, service):
        with pytest.raises(ValidationError, match="missing required keys"):
            service.create_memory(
                memory_id="mem-1",
                snapshot={"invalid": True},
                actor_type="human",
                executed_by="zserverai",
                initiated_by="zserverai",
            )
    
    def test_create_validates_actor(self, service):
        snapshot = _make_snapshot()
        with pytest.raises(ValidationError, match="requires initiated_by"):
            service.create_memory(
                memory_id="mem-1",
                snapshot=snapshot,
                actor_type="human",
                executed_by="zserverai",
                initiated_by=None,
            )


class TestUpdateMemory:
    def test_update_success(self, service):
        snapshot = _make_snapshot()
        create_result = service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        updated_snapshot = _make_snapshot(title="Updated Test")
        update_result = service.update_memory(
            memory_id="mem-1",
            snapshot=updated_snapshot,
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert update_result.changed is True
        assert update_result.entry.version == 2
        assert update_result.entry.snapshot["title"] == "Updated Test"
    
    def test_update_noop(self, service):
        snapshot = _make_snapshot()
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        result = service.update_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert result.changed is False
        assert result.entry.version == 1
    
    def test_update_version_conflict(self, service):
        snapshot = _make_snapshot()
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        with pytest.raises(VersionConflictError) as exc_info:
            service.update_memory(
                memory_id="mem-1",
                snapshot=_make_snapshot(title="Conflict"),
                expected_version=99,
                actor_type="human",
                executed_by="zserverai",
                initiated_by="zserverai",
            )
        
        assert exc_info.value.expected == 99
        assert exc_info.value.current == 1


class TestChangeStatus:
    def test_status_transition_draft_to_approved(self, service):
        snapshot = _make_snapshot(status="draft")
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        result = service.change_status(
            memory_id="mem-1",
            new_status="approved",
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert result.changed is True
        assert result.entry.snapshot["status"] == "approved"
    
    def test_status_transition_invalid(self, service):
        snapshot = _make_snapshot(status="draft")
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        with pytest.raises(InvalidTransitionError):
            service.change_status(
                memory_id="mem-1",
                new_status="superseded",
                expected_version=1,
                actor_type="human",
                executed_by="zserverai",
                initiated_by="zserverai",
            )


class TestDeleteMemory:
    def test_delete_success(self, service):
        snapshot = _make_snapshot()
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        result = service.delete_memory(
            memory_id="mem-1",
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert result.changed is True
        assert result.entry.change_type == "delete"
        assert result.entry.snapshot["deleted"] is True
    
    def test_delete_already_deleted(self, service):
        snapshot = _make_snapshot()
        service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        service.delete_memory(
            memory_id="mem-1",
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        with pytest.raises(DeletedMemoryError):
            service.delete_memory(
                memory_id="mem-1",
                expected_version=2,
                actor_type="human",
                executed_by="zserverai",
                initiated_by="zserverai",
            )


class TestRollback:
    def test_rollback_restores(self, service):
        # Create with v1
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="Original"),
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        # Update to v2
        service.update_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="Modified"),
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        # Rollback to v1
        result = service.rollback(
            memory_id="mem-1",
            target_version=1,
            expected_version=2,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert result.changed is True
        assert result.entry.change_type == "rollback"
        assert result.entry.snapshot["title"] == "Original"
        assert result.entry.version == 3
    
    def test_rollback_to_tombstone(self, service):
        # Create
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(),
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        # Delete
        service.delete_memory(
            memory_id="mem-1",
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        # Rollback to v1 (restore)
        result = service.rollback(
            memory_id="mem-1",
            target_version=1,
            expected_version=2,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        assert result.entry.snapshot["deleted"] is False


class TestIdempotency:
    def test_repeated_change_id(self, service):
        snapshot = _make_snapshot()
        result1 = service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
            change_id="test-change-id",
        )
        
        result2 = service.create_memory(
            memory_id="mem-1",
            snapshot=snapshot,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
            change_id="test-change-id",
        )
        
        assert result1.entry.id == result2.entry.id
        assert result2.changed is False


class TestDiff:
    def test_diff_versions(self, service):
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="V1", importance=1),
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        service.update_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="V2", importance=5),
            expected_version=1,
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        diffs = service.diff_versions("mem-1", 1, 2)
        
        assert len(diffs) == 2
        fields = {d.field for d in diffs}
        assert "title" in fields
        assert "importance" in fields


class TestConcurrency:
    def test_concurrent_updates(self, service):
        """Two concurrent updates: exactly one succeeds."""
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(),
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        results = []
        errors = []
        
        def update_thread(thread_id):
            try:
                conn = sqlite3.connect(service.db.execute("PRAGMA database_list").fetchone()[0][2])
                svc = HistoryService(conn)
                result = svc.update_memory(
                    memory_id="mem-1",
                    snapshot=_make_snapshot(title=f"Thread {thread_id}"),
                    expected_version=1,
                    actor_type="human",
                    executed_by="zserverai",
                    initiated_by="zserverai",
                )
                results.append(result)
            except VersionConflictError as e:
                errors.append(e)
            finally:
                conn.close()
        
        t1 = threading.Thread(target=update_thread, args=(1,))
        t2 = threading.Thread(target=update_thread, args=(2,))
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # Exactly one succeeds, one gets conflict
        assert len(results) == 1
        assert len(errors) == 1
```

- [ ] **Step 4: Run unit tests**

Run: `pytest tests/test_history.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add memory/history.py tests/test_history.py
git commit -m "feat: add HistoryService with versioned tracking"
```

---

### Task 3: Models and CRUD Updates

**Files:**
- Modify: `memory/models.py`
- Modify: `memory/crud.py`
- Test: `tests/test_crud.py`

**Interfaces:**
- Consumes: HistoryService (from Task 2)
- Produces: Updated `MemoryResponse`, new Pydantic models for history

- [ ] **Step 1: Add deleted_at to MemoryResponse**

Modify `memory/models.py`:

```python
# Add to MemoryResponse class
class MemoryResponse(BaseModel):
    id: str
    type: str
    title: str
    content: str
    source: str
    importance: int
    tags: list[str]
    created_at: str
    updated_at: str
    accessed_at: str | None = None
    access_count: int = 0
    archived: bool = False
    vault_path: str | None = None
    score: float | None = None
    deleted_at: str | None = None  # NEW
    status: str | None = None
    content_hash: str | None = None
    source_type: str | None = None
    source_uri: str | None = None
    captured_at: str | None = None
    confidentiality: str | None = None
```

- [ ] **Step 2: Add history Pydantic models**

Append to `memory/models.py`:

```python
class HistoryEntryResponse(BaseModel):
    id: str
    memory_id: str
    version: int
    change_id: str
    actor_type: str
    initiated_by: str | None = None
    executed_by: str
    change_type: str
    reason: str | None = None
    snapshot: dict
    rolled_back_from_history_id: str | None = None
    created_at: str


class FieldDiffResponse(BaseModel):
    field: str
    old_value: Any
    new_value: Any


class HistoryListResponse(BaseModel):
    entries: list[HistoryEntryResponse]
    total: int
    limit: int
    offset: int


class RollbackRequest(BaseModel):
    target_version: int
    expected_version: int
    actor_type: str
    executed_by: str
    initiated_by: str | None = None
    reason: str | None = None
    change_id: str | None = None


class MutationResponse(BaseModel):
    changed: bool
    entry: HistoryEntryResponse
    git_commit_sha: str | None = None
    git_warning: str | None = None
```

- [ ] **Step 3: Update _row_to_memory for deleted_at**

Modify `memory/crud.py` `_row_to_memory` function to handle `deleted_at`:

```python
def _row_to_memory(row):
    """Convert a database row to MemoryResponse."""
    # ... existing code ...
    # Add deleted_at handling
    deleted_at = None
    if len(row) > 15:  # Check if column exists
        deleted_at = row[15]  # Assuming deleted_at is at index 15
    
    return MemoryResponse(
        # ... existing fields ...
        deleted_at=deleted_at,
    )
```

- [ ] **Step 4: Run CRUD tests**

Run: `pytest tests/test_crud.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add memory/models.py memory/crud.py tests/test_crud.py
git commit -m "feat: add history models and update CRUD for deleted_at"
```

---

### Task 4: Git Integration

**Files:**
- Modify: `memory/review.py`
- Test: `tests/test_git_integration.py` (new)

**Interfaces:**
- Consumes: `HistoryService.MutationResult`
- Produces: `git_commit_with_history()` function

- [ ] **Step 1: Add git_commit_with_history function**

Modify `memory/review.py`:

```python
import subprocess
from pathlib import Path


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
```

- [ ] **Step 2: Write git integration tests**

Create `tests/test_git_integration.py`:

```python
"""Tests for Git integration with history."""

import subprocess
import tempfile
import os
import pytest
from pathlib import Path
from memory.review import git_commit_with_history


@pytest.fixture
def git_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        
        # Create initial commit
        (repo_path / "README.md").write_text("Initial")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
        
        yield repo_path


def test_commit_with_history_success(git_repo):
    """Test successful commit with history."""
    # Create a file
    test_file = git_repo / "test.md"
    test_file.write_text("Test content")
    
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id",
        memory_id="mem-1",
        change_type="create",
        memory_title="Test Memory",
    )
    
    assert sha is not None
    assert len(sha) == 40  # Valid SHA
    
    # Verify commit message
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "create: Test Memory" in result.stdout
    assert "Memory-Id: mem-1" in result.stdout
    assert "Memory-Change-Id: test-change-id" in result.stdout


def test_commit_preserves_staged(git_repo):
    """Test that existing staged changes are preserved."""
    # Stage an unrelated change
    unrelated_file = git_repo / "unrelated.txt"
    unrelated_file.write_text("Unrelated")
    subprocess.run(["git", "add", str(unrelated_file)], cwd=git_repo, check=True)
    
    # Now commit a different file
    test_file = git_repo / "test.md"
    test_file.write_text("Test content")
    
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id-2",
        memory_id="mem-2",
        change_type="update",
        memory_title="Test Memory 2",
    )
    
    # Verify unrelated file is still staged
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    assert "unrelated.txt" in result.stdout


def test_commit_no_changes(git_repo):
    """Test skip when no changes in affected paths."""
    test_file = git_repo / "test.md"
    test_file.write_text("No changes")
    
    # Commit it
    subprocess.run(["git", "add", str(test_file)], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_repo, check=True)
    
    # Try to commit again with no changes
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[test_file],
        change_id="test-change-id-3",
        memory_id="mem-3",
        change_type="update",
        memory_title="Test Memory 3",
    )
    
    assert sha is None


def test_commit_failure_returns_none(git_repo):
    """Test that git failure returns None, not exception."""
    # Try to commit to non-existent path
    sha = git_commit_with_history(
        vault_path=git_repo,
        affected_paths=[Path("nonexistent.md")],
        change_id="test-change-id-4",
        memory_id="mem-4",
        change_type="create",
        memory_title="Test Memory 4",
    )
    
    # Should return None, not raise
    assert sha is None
```

- [ ] **Step 3: Run git integration tests**

Run: `pytest tests/test_git_integration.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add memory/review.py tests/test_git_integration.py
git commit -m "feat: add git_commit_with_history for isolated commits"
```

---

### Task 5: CLI History Commands

**Files:**
- Modify: `memory/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `HistoryService`, `git_commit_with_history`
- Produces: `history list`, `history diff`, `history rollback` subcommands

- [ ] **Step 1: Add history subcommand group**

Modify `memory/cli.py` to add history subcommands:

```python
# Add to parser setup
history_parser = sub.add_parser("history", help="Memory history operations")
history_sub = history_parser.add_subparsers(dest="history_cmd")

# history list
history_list = history_sub.add_parser("list", help="List history for a memory")
history_list.add_argument("memory_id", help="Memory ID")
history_list.add_argument("--limit", type=int, default=50)
history_list.add_argument("--offset", type=int, default=0)
history_list.add_argument("--json", action="store_true")

# history diff
history_diff = history_sub.add_parser("diff", help="Compare two versions")
history_diff.add_argument("memory_id", help="Memory ID")
history_diff.add_argument("version_a", type=int, help="First version")
history_diff.add_argument("version_b", type=int, help="Second version")
history_diff.add_argument("--json", action="store_true")

# history rollback
history_rollback = history_sub.add_parser("rollback", help="Rollback to a version")
history_rollback.add_argument("memory_id", help="Memory ID")
history_rollback.add_argument("target_version", type=int, help="Version to restore")
history_rollback.add_argument("--expected-version", type=int, help="Expected current version")
history_rollback.add_argument("--actor-type", default="human", choices=["human", "agent", "system"])
history_rollback.add_argument("--executed-by", help="Executor identity")
history_rollback.add_argument("--reason", help="Reason for rollback")
history_rollback.add_argument("--yes", action="store_true", help="Skip confirmation")
```

- [ ] **Step 2: Implement history command handlers**

Add to `memory/cli.py`:

```python
import getpass
from memory.history import HistoryService, MemoryNotFoundError, VersionConflictError
from memory.review import git_commit_with_history


def cmd_history(args, vault_path):
    """Handle history subcommands."""
    db = get_db(vault_path)
    service = HistoryService(db)
    
    if args.history_cmd == "list":
        return cmd_history_list(args, service)
    elif args.history_cmd == "diff":
        return cmd_history_diff(args, service)
    elif args.history_cmd == "rollback":
        return cmd_history_rollback(args, service, vault_path)
    else:
        print("error: history command required (list, diff, rollback)", file=sys.stderr)
        return 1


def cmd_history_list(args, service):
    """List history for a memory."""
    entries = service.get_log(
        memory_id=args.memory_id,
        limit=args.limit,
        offset=args.offset,
    )
    
    if args.json:
        import json
        output = {
            "entries": [
                {
                    "id": e.id,
                    "memory_id": e.memory_id,
                    "version": e.version,
                    "change_id": e.change_id,
                    "actor_type": e.actor_type,
                    "initiated_by": e.initiated_by,
                    "executed_by": e.executed_by,
                    "change_type": e.change_type,
                    "reason": e.reason,
                    "snapshot": e.snapshot,
                    "rolled_back_from_history_id": e.rolled_back_from_history_id,
                    "created_at": e.created_at,
                }
                for e in entries
            ],
            "total": len(entries),
            "limit": args.limit,
            "offset": args.offset,
        }
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"{'Version':<8} {'Author':<20} {'Type':<15} {'Reason':<25} {'Date':<20}")
        print("-" * 90)
        for e in entries:
            author = e.executed_by or "unknown"
            reason = (e.reason or "")[:24]
            date = e.created_at[:19]
            print(f"{e.version:<8} {author:<20} {e.change_type:<15} {reason:<25} {date:<20}")
    
    return 0


def cmd_history_diff(args, service):
    """Compare two versions."""
    try:
        diffs = service.diff_versions(args.memory_id, args.version_a, args.version_b)
    except MemoryNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    
    if args.json:
        import json
        output = [
            {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
            for d in diffs
        ]
        print(json.dumps(output, indent=2))
    else:
        if not diffs:
            print("No differences found.")
            return 0
        
        print(f"{'Field':<15} {'Old':<30} {'New':<30}")
        print("-" * 75)
        for d in diffs:
            old = str(d.old_value)[:29]
            new = str(d.new_value)[:29]
            print(f"{d.field:<15} {old:<30} {new:<30}")
    
    return 0


def cmd_history_rollback(args, service, vault_path):
    """Rollback to a specific version."""
    import sys
    
    # Get current version if not specified
    if args.expected_version is None:
        entries = service.get_log(memory_id=args.memory_id, limit=1)
        if entries:
            args.expected_version = entries[0].version
        else:
            print("error: no history found for memory", file=sys.stderr)
            return 1
    
    # Confirm unless --yes
    if not args.yes:
        diffs = service.diff_versions(args.memory_id, args.expected_version, args.target_version)
        
        print("Proposed rollback:")
        print(f"  Memory: {args.memory_id}")
        print(f"  From version: {args.expected_version}")
        print(f"  To version: {args.target_version}")
        
        if diffs:
            print("\nChanges:")
            for d in diffs:
                print(f"  {d.field}: {d.old_value} -> {d.new_value}")
        
        response = input("\nProceed? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            return 0
    
    # Default attribution
    executed_by = args.executed_by or getpass.getuser()
    initiated_by = getpass.getuser() if args.actor_type == "human" else None
    
    try:
        result = service.rollback(
            memory_id=args.memory_id,
            target_version=args.target_version,
            expected_version=args.expected_version,
            actor_type=args.actor_type,
            executed_by=executed_by,
            initiated_by=initiated_by,
            reason=args.reason,
        )
    except (MemoryNotFoundError, VersionConflictError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2 if isinstance(e, VersionConflictError) else 1
    
    # Git integration
    git_sha = None
    git_warning = None
    
    if result.changed and result.entry.snapshot.get("vault_path"):
        vault_file = Path(vault_path) / result.entry.snapshot["vault_path"]
        if vault_file.exists():
            git_sha = git_commit_with_history(
                vault_path=Path(vault_path),
                affected_paths=[vault_file],
                change_id=result.entry.change_id,
                memory_id=args.memory_id,
                change_type="rollback",
                memory_title=result.entry.snapshot["title"],
            )
            if git_sha is None:
                git_warning = "git commit failed, database change preserved"
    
    # Output
    if args.json:
        import json
        output = {
            "changed": result.changed,
            "entry": {
                "id": result.entry.id,
                "memory_id": result.entry.memory_id,
                "version": result.entry.version,
                "change_id": result.entry.change_id,
                "change_type": result.entry.change_type,
            },
            "git_commit_sha": git_sha,
            "git_warning": git_warning,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Rollback complete: version {result.entry.version}")
        if git_sha:
            print(f"Git commit: {git_sha}")
        if git_warning:
            print(f"warning: {git_warning}", file=sys.stderr)
    
    return 0


# Update cmd_map to include history
cmd_map = {
    # ... existing commands ...
    "history": cmd_history,
}
```

- [ ] **Step 3: Write CLI tests**

Add to `tests/test_cli.py`:

```python
def test_history_list(db, service):
    """Test history list command."""
    from memory.history import HistoryService
    
    # Create test data
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    args = argparse.Namespace(
        history_cmd="list",
        memory_id="mem-1",
        limit=50,
        offset=0,
        json=False,
    )
    
    result = cmd_history(args, str(tmpdir))
    assert result == 0


def test_history_diff(db, service):
    """Test history diff command."""
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V1"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    service.update_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V2"),
        expected_version=1,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    args = argparse.Namespace(
        history_cmd="diff",
        memory_id="mem-1",
        version_a=1,
        version_b=2,
        json=False,
    )
    
    result = cmd_history(args, str(tmpdir))
    assert result == 0
```

- [ ] **Step 4: Run CLI tests**

Run: `pytest tests/test_cli.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add memory/cli.py tests/test_cli.py
git commit -m "feat: add history CLI commands with Git integration"
```

---

### Task 6: MCP History Tools

**Files:**
- Modify: `memory/mcp/server.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- Consumes: `HistoryService`
- Produces: `list_memory_history`, `diff_memory_history`, `rollback_memory` tools

- [ ] **Step 1: Add history tools to MCP server**

Modify `memory/mcp/server.py`:

```python
# Add to tools list
HISTORY_TOOLS = [
    {
        "name": "list_memory_history",
        "description": "List history for a memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["memory_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diff_memory_history",
        "description": "Compare two versions of a memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "version_a": {"type": "integer", "minimum": 1},
                "version_b": {"type": "integer", "minimum": 1},
            },
            "required": ["memory_id", "version_a", "version_b"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rollback_memory",
        "description": "Rollback a memory to a previous version",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "target_version": {"type": "integer", "minimum": 1},
                "expected_version": {"type": "integer", "minimum": 1},
                "actor_type": {"type": "string", "enum": ["human", "agent", "system"]},
                "executed_by": {"type": "string", "minLength": 1},
                "initiated_by": {"type": "string"},
                "reason": {"type": "string"},
                "change_id": {"type": ["string", "null"]},
            },
            "required": ["memory_id", "target_version", "expected_version", "actor_type", "executed_by"],
            "if": {"properties": {"actor_type": {"const": "agent"}}},
            "then": {"required": ["reason"]},
            "additionalProperties": False,
        },
    },
]


# Add to handle_request for tools/list
def handle_list_tools(read_only: bool) -> dict:
    """Return available tools based on read-only mode."""
    tools = [
        # ... existing tools ...
    ]
    
    if not read_only:
        tools.extend(HISTORY_TOOLS)
    
    return {"tools": tools}


# Add to handle_tools_call
def handle_history_tools(method: str, params: dict, vault_path: str, read_only: bool) -> dict:
    """Handle history tool calls."""
    from memory.history import HistoryService, MemoryNotFoundError, VersionConflictError
    
    db = get_db(vault_path)
    service = HistoryService(db)
    
    if method == "list_memory_history":
        entries = service.get_log(
            memory_id=params["memory_id"],
            limit=params.get("limit", 50),
            offset=params.get("offset", 0),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        [
                            {
                                "id": e.id,
                                "memory_id": e.memory_id,
                                "version": e.version,
                                "change_id": e.change_id,
                                "change_type": e.change_type,
                                "executed_by": e.executed_by,
                                "created_at": e.created_at,
                            }
                            for e in entries
                        ]
                    ),
                }
            ]
        }
    
    elif method == "diff_memory_history":
        diffs = service.diff_versions(
            params["memory_id"],
            params["version_a"],
            params["version_b"],
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        [
                            {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
                            for d in diffs
                        ]
                    ),
                }
            ]
        }
    
    elif method == "rollback_memory":
        if read_only:
            return {
                "error": {
                    "code": "read_only",
                    "message": "Rollback blocked in read-only mode",
                }
            }
        
        try:
            result = service.rollback(
                memory_id=params["memory_id"],
                target_version=params["target_version"],
                expected_version=params["expected_version"],
                actor_type=params["actor_type"],
                executed_by=params["executed_by"],
                initiated_by=params.get("initiated_by"),
                change_id=params.get("change_id"),
                reason=params.get("reason"),
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "changed": result.changed,
                                "entry": {
                                    "id": result.entry.id,
                                    "version": result.entry.version,
                                    "change_id": result.entry.change_id,
                                },
                            }
                        ),
                    }
                ]
            }
        except (MemoryNotFoundError, VersionConflictError) as e:
            return {
                "error": {
                    "code": "version_conflict" if isinstance(e, VersionConflictError) else "not_found",
                    "message": str(e),
                }
            }
```

- [ ] **Step 2: Write MCP tests**

Add to `tests/test_mcp.py`:

```python
def test_list_memory_history(vault_path, service):
    """Test list_memory_history tool."""
    from memory.mcp.server import handle_history_tools
    
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    result = handle_history_tools(
        "list_memory_history",
        {"memory_id": "mem-1"},
        vault_path,
        read_only=False,
    )
    
    assert "content" in result
    assert len(result["content"]) > 0


def test_rollback_blocked_in_read_only(vault_path, service):
    """Test rollback is blocked in read-only mode."""
    from memory.mcp.server import handle_history_tools
    
    result = handle_history_tools(
        "rollback_memory",
        {"memory_id": "mem-1", "target_version": 1, "expected_version": 1, "actor_type": "human", "executed_by": "test"},
        vault_path,
        read_only=True,
    )
    
    assert "error" in result
    assert result["error"]["code"] == "read_only"
```

- [ ] **Step 3: Run MCP tests**

Run: `pytest tests/test_mcp.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add memory/mcp/server.py tests/test_mcp.py
git commit -m "feat: add history MCP tools with read-only blocking"
```

---

### Task 7: REST API History Endpoints

**Files:**
- Modify: `memory/api/server.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `HistoryService`
- Produces: 3 new REST endpoints

- [ ] **Step 1: Add history endpoints**

Modify `memory/api/server.py`:

```python
from memory.history import HistoryService, MemoryNotFoundError, VersionConflictError
from memory.models import HistoryEntryResponse, HistoryListResponse, MutationResponse, RollbackRequest


@app.get("/v1/memories/{memory_id}/history", response_model=HistoryListResponse)
def list_history(
    memory_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    """List history for a memory."""
    service = HistoryService(db)
    entries = service.get_log(memory_id=memory_id, limit=limit, offset=offset)
    
    return HistoryListResponse(
        entries=[
            HistoryEntryResponse(
                id=e.id,
                memory_id=e.memory_id,
                version=e.version,
                change_id=e.change_id,
                actor_type=e.actor_type,
                initiated_by=e.initiated_by,
                executed_by=e.executed_by,
                change_type=e.change_type,
                reason=e.reason,
                snapshot=e.snapshot,
                rolled_back_from_history_id=e.rolled_back_from_history_id,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=len(entries),
        limit=limit,
        offset=offset,
    )


@app.get("/v1/memories/{memory_id}/history/diff")
def diff_history(
    memory_id: str,
    a: int = Query(..., ge=1),
    b: int = Query(..., ge=1),
    db: sqlite3.Connection = Depends(get_db),
):
    """Compare two versions of a memory."""
    service = HistoryService(db)
    
    try:
        diffs = service.diff_versions(memory_id, a, b)
    except MemoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return [
        {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
        for d in diffs
    ]


@app.post("/v1/memories/{memory_id}/history/rollback", response_model=MutationResponse)
def rollback_history(
    memory_id: str,
    request: RollbackRequest,
    idempotency_key: str | None = Header(None),
    db: sqlite3.Connection = Depends(get_db),
    read_only: bool = Depends(get_read_only),
):
    """Rollback a memory to a previous version."""
    if read_only:
        raise HTTPException(status_code=403, detail="Rollback blocked in read-only mode")
    
    service = HistoryService(db)
    
    try:
        result = service.rollback(
            memory_id=memory_id,
            target_version=request.target_version,
            expected_version=request.expected_version,
            actor_type=request.actor_type,
            executed_by=request.executed_by,
            initiated_by=request.initiated_by,
            change_id=idempotency_key or request.change_id,
            reason=request.reason,
        )
    except MemoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except VersionConflictError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "version_conflict",
                "message": str(e),
                "details": {"current_version": e.current},
            },
        )
    
    return MutationResponse(
        changed=result.changed,
        entry=HistoryEntryResponse(
            id=result.entry.id,
            memory_id=result.entry.memory_id,
            version=result.entry.version,
            change_id=result.entry.change_id,
            actor_type=result.entry.actor_type,
            initiated_by=result.entry.initiated_by,
            executed_by=result.entry.executed_by,
            change_type=result.entry.change_type,
            reason=result.entry.reason,
            snapshot=result.entry.snapshot,
            rolled_back_from_history_id=result.entry.rolled_back_from_history_id,
            created_at=result.entry.created_at,
        ),
        git_commit_sha=None,
        git_warning=None,
    )
```

- [ ] **Step 2: Write API tests**

Add to `tests/test_api.py`:

```python
def test_list_history(client, service):
    """Test GET /v1/memories/{id}/history"""
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    response = client.get("/v1/memories/mem-1/history")
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert len(data["entries"]) == 1


def test_diff_history(client, service):
    """Test GET /v1/memories/{id}/history/diff"""
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V1"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    service.update_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V2"),
        expected_version=1,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    response = client.get("/v1/memories/mem-1/history/diff?a=1&b=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0


def test_rollback_history(client, service):
    """Test POST /v1/memories/{id}/history/rollback"""
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V1"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )
    
    response = client.post(
        "/v1/memories/mem-1/history/rollback",
        json={
            "target_version": 1,
            "expected_version": 1,
            "actor_type": "human",
            "executed_by": "zserverai",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["changed"] is True
```

- [ ] **Step 3: Run API tests**

Run: `pytest tests/test_api.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add memory/api/server.py tests/test_api.py
git commit -m "feat: add history REST endpoints with auth"
```

---

### Task 8: Integration and E2E Test

**Files:**
- Test: `tests/test_history.py` (extend)

**Interfaces:**
- Consumes: All previous tasks
- Produces: E2E workflow test

- [ ] **Step 1: Write E2E workflow test**

Add to `tests/test_history.py`:

```python
def test_e2e_full_workflow(service):
    """Full workflow: create → update → status transition → soft deletion → diff → rollback."""
    # Create
    result = service.create_memory(
        memory_id="e2e-1",
        snapshot=_make_snapshot(title="E2E Test", status="draft"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
        reason="Initial creation",
    )
    assert result.changed is True
    assert result.entry.version == 1
    
    # Update
    result = service.update_memory(
        memory_id="e2e-1",
        snapshot=_make_snapshot(title="E2E Test Updated", status="draft"),
        expected_version=1,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
        reason="Added content",
    )
    assert result.entry.version == 2
    
    # Status transition
    result = service.change_status(
        memory_id="e2e-1",
        new_status="approved",
        expected_version=2,
        actor_type="human",
        executed_by="helium-review",
        initiated_by="zserverai",
        reason="Approved for production",
    )
    assert result.entry.version == 3
    assert result.entry.snapshot["status"] == "approved"
    
    # Delete
    result = service.delete_memory(
        memory_id="e2e-1",
        expected_version=3,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
        reason="No longer needed",
    )
    assert result.entry.version == 4
    assert result.entry.snapshot["deleted"] is True
    
    # Diff between v1 and v2
    diffs = service.diff_versions("e2e-1", 1, 2)
    assert any(d.field == "title" for d in diffs)
    
    # Rollback to v1
    result = service.rollback(
        memory_id="e2e-1",
        target_version=1,
        expected_version=4,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
        reason="Restore original",
    )
    assert result.entry.version == 5
    assert result.entry.change_type == "rollback"
    assert result.entry.snapshot["title"] == "E2E Test"
    assert result.entry.snapshot["deleted"] is False
    
    # Verify full history
    log = service.get_log(memory_id="e2e-1")
    assert len(log) == 5
    assert [e.change_type for e in log] == ["rollback", "delete", "status_change", "update", "create"]
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_history.py
git commit -m "test: add E2E workflow test for history"
```

---

## Self-Review Checklist

- [ ] All spec requirements covered by tasks
- [ ] No placeholders or TODOs in plan
- [ ] Type signatures consistent across tasks
- [ ] File paths exact and complete
- [ ] Commands have expected output
- [ ] Each task produces independently testable deliverable
