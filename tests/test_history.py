"""Tests for memory history service."""

import json
import sqlite3
import tempfile
import threading
from pathlib import Path

import pytest

from memory.database import _local, init_db
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
    _local.conn = None
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir)
        init_db(db_path)
        yield _local.conn
        if _local.conn is not None:
            _local.conn.close()
            _local.conn = None


@pytest.fixture
def service(db):
    """Create HistoryService with test database."""
    return HistoryService(db)


def _make_snapshot(title="Test", status="draft", tags=None, importance=1, deleted=False, content=None):
    """Create a valid snapshot for testing."""
    return {
        "schema_version": 1,
        "title": title,
        "content": content if content is not None else f"# {title}\n\nContent here.",
        "status": status,
        "tags": tags or [],
        "importance": importance,
        "vault_path": "test/test.md",
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
        service.create_memory(
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
            snapshot=_make_snapshot(title="V1", importance=1, content="Same content"),
            actor_type="human",
            executed_by="zserverai",
            initiated_by="zserverai",
        )
        
        service.update_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="V2", importance=5, content="Same content"),
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
        
        db_path = service.db.execute("PRAGMA database_list").fetchone()[2]
        
        results = []
        errors = []
        
        def update_thread(thread_id):
            conn = None
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
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
                if conn is not None:
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