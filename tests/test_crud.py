import tempfile
from pathlib import Path

import pytest

from memory.crud import archive, create, get, get_stats, update, upsert_by_vault_path
from memory.database import _local, init_db
from memory.models import MemoryCreate, MemoryUpdate


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
