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
            "title": row["title"],
            "content": row["content"],
            "status": new_status,
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "importance": row["importance"],
            "vault_path": row["vault_path"],
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
        
        if row["deleted_at"] is not None:
            raise DeletedMemoryError(f"Memory {memory_id} is already deleted")
        
        # Build tombstone snapshot
        snapshot = {
            "schema_version": 1,
            "title": row["title"],
            "content": row["content"],
            "status": row["status"],
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "importance": row["importance"],
            "vault_path": row["vault_path"],
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
        
        target_history_id = target["id"]
        target_snapshot = json.loads(target["snapshot"])
        
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
                id=row["id"],
                memory_id=row["memory_id"],
                version=row["version"],
                change_id=row["change_id"],
                actor_type=row["actor_type"],
                initiated_by=row["initiated_by"],
                executed_by=row["executed_by"],
                change_type=row["change_type"],
                reason=row["reason"],
                snapshot=json.loads(row["snapshot"]),
                rolled_back_from_history_id=row["rolled_back_from_history_id"],
                created_at=row["created_at"],
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
        
        snap_a = json.loads(row_a["snapshot"])
        snap_b = json.loads(row_b["snapshot"])
        
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
                    id=existing["id"],
                    memory_id=existing["memory_id"],
                    version=existing["version"],
                    change_id=existing["change_id"],
                    actor_type=existing["actor_type"],
                    initiated_by=existing["initiated_by"],
                    executed_by=existing["executed_by"],
                    change_type=existing["change_type"],
                    reason=existing["reason"],
                    snapshot=json.loads(existing["snapshot"]),
                    rolled_back_from_history_id=existing["rolled_back_from_history_id"],
                    created_at=existing["created_at"],
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
                    current_snapshot = json.loads(current_row["snapshot"])
                    if not _snapshots_differ(current_snapshot, snapshot):
                        # No-op: return existing entry
                        entry_row = self.db.execute(
                            "SELECT id, memory_id, version, change_id, actor_type, initiated_by, "
                            "executed_by, change_type, reason, snapshot, rolled_back_from_history_id, created_at "
                            "FROM memory_history WHERE memory_id = ? AND version = ?",
                            (memory_id, current_version),
                        ).fetchone()
                        entry = HistoryEntry(
                            id=entry_row["id"],
                            memory_id=entry_row["memory_id"],
                            version=entry_row["version"],
                            change_id=entry_row["change_id"],
                            actor_type=entry_row["actor_type"],
                            initiated_by=entry_row["initiated_by"],
                            executed_by=entry_row["executed_by"],
                            change_type=entry_row["change_type"],
                            reason=entry_row["reason"],
                            snapshot=json.loads(entry_row["snapshot"]),
                            rolled_back_from_history_id=entry_row["rolled_back_from_history_id"],
                            created_at=entry_row["created_at"],
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