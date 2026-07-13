import tempfile
from pathlib import Path

import pytest

from memory.crud import archive, create, get, get_stats, update, upsert_by_vault_path
from memory.database import _local, init_db
from memory.models import (
    FieldDiffResponse,
    HistoryEntryResponse,
    HistoryListResponse,
    MemoryCreate,
    MemoryUpdate,
    MutationResponse,
    RollbackRequest,
)


@pytest.fixture
def vault():
    _local.conn = None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        init_db(path)
        yield path
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


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


def test_deleted_at_is_none_by_default(vault):
    m = create(vault, MemoryCreate(title="No delete"))
    assert m.deleted_at is None


def test_deleted_at_populated_on_archive(vault):
    m = create(vault, MemoryCreate(title="Will archive"))
    archive(vault, m.id)
    db = (vault / "data" / "memory.db").resolve()
    from memory.crud import _row_to_memory
    from memory.database import get_db
    conn = get_db(vault)
    row = conn.execute("SELECT * FROM memories WHERE id=?", (m.id,)).fetchone()
    assert row["deleted_at"] is not None
    mem = _row_to_memory(row)
    assert mem.deleted_at is not None


def test_memory_response_has_expected_fields(vault):
    m = create(vault, MemoryCreate(title="Full fields"))
    assert m.status == "approved"
    assert m.content_hash is None
    assert m.source_type == "manual"
    assert m.source_uri is None
    assert m.captured_at is None
    assert m.confidentiality == "confidential"


def test_history_entry_response_model():
    entry = HistoryEntryResponse(
        id="abc123",
        memory_id="mem1",
        version=1,
        change_id="chg1",
        actor_type="human",
        initiated_by="alice",
        executed_by="agent",
        change_type="create",
        reason="Initial",
        snapshot={"title": "Test"},
        created_at="2025-01-01T00:00:00Z",
    )
    assert entry.id == "abc123"
    assert entry.memory_id == "mem1"
    assert entry.version == 1
    assert entry.actor_type == "human"
    assert entry.initiated_by == "alice"
    assert entry.rolled_back_from_history_id is None


def test_field_diff_response_model():
    diff = FieldDiffResponse(field="title", old_value="Old", new_value="New")
    assert diff.field == "title"
    assert diff.old_value == "Old"
    assert diff.new_value == "New"


def test_history_list_response_model():
    entry = HistoryEntryResponse(
        id="e1",
        memory_id="m1",
        version=1,
        change_id="c1",
        actor_type="agent",
        executed_by="bot",
        change_type="create",
        snapshot={},
        created_at="2025-01-01T00:00:00Z",
    )
    resp = HistoryListResponse(entries=[entry], total=1, limit=50, offset=0)
    assert len(resp.entries) == 1
    assert resp.total == 1


def test_rollback_request_model():
    req = RollbackRequest(
        target_version=1,
        expected_version=3,
        actor_type="human",
        executed_by="alice",
        reason="Revert bad edit",
    )
    assert req.target_version == 1
    assert req.expected_version == 3
    assert req.change_id is None


def test_mutation_response_model():
    entry = HistoryEntryResponse(
        id="e1",
        memory_id="m1",
        version=1,
        change_id="c1",
        actor_type="agent",
        executed_by="bot",
        change_type="create",
        snapshot={},
        created_at="2025-01-01T00:00:00Z",
    )
    resp = MutationResponse(changed=True, entry=entry)
    assert resp.changed is True
    assert resp.git_commit_sha is None
    assert resp.git_warning is None
