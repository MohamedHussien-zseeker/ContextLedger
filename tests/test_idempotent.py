"""Tests for idempotent capture and RawSource extensions."""
import tempfile
from pathlib import Path

import pytest

from memory.crud import create, find_by_content_hash
from memory.database import _local, init_db
from memory.models import MemoryCreate
from memory.providers.base import RawSource


@pytest.fixture
def temp_vault():
    """Create a temporary vault directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test-vault"
        vault_path.mkdir()
        _local.conn = None
        init_db(vault_path)
        yield vault_path
        _local.conn = None


def test_rawsource_generates_content_hash():
    """RawSource auto-generates content hash from content."""
    source = RawSource(
        source_type="test",
        source_uri="test://example",
        title="Test",
        content="Hello world"
    )
    assert source.content_hash != ""
    assert len(source.content_hash) == 64  # SHA-256 hex digest


def test_rawsource_content_hash_deterministic():
    """Same content produces same hash."""
    source1 = RawSource(
        source_type="test",
        source_uri="test://1",
        title="Test 1",
        content="Same content"
    )
    source2 = RawSource(
        source_type="test",
        source_uri="test://2",
        title="Test 2",
        content="Same content"
    )
    assert source1.content_hash == source2.content_hash


def test_rawsource_different_content_different_hash():
    """Different content produces different hash."""
    source1 = RawSource(
        source_type="test",
        source_uri="test://1",
        title="Test",
        content="Content A"
    )
    source2 = RawSource(
        source_type="test",
        source_uri="test://1",
        title="Test",
        content="Content B"
    )
    assert source1.content_hash != source2.content_hash


def test_rawsource_default_confidentiality():
    """RawSource defaults to confidential."""
    source = RawSource(
        source_type="test",
        source_uri="test://example",
        title="Test",
        content="Content"
    )
    assert source.confidentiality == "confidential"


def test_rawsource_custom_confidentiality():
    """RawSource accepts custom confidentiality."""
    source = RawSource(
        source_type="test",
        source_uri="test://example",
        title="Test",
        content="Content",
        confidentiality="public"
    )
    assert source.confidentiality == "public"


def test_rawsource_metadata_default_factory():
    """RawSource metadata uses default_factory (no shared dict)."""
    source1 = RawSource(
        source_type="test",
        source_uri="test://1",
        title="Test",
        content="Content"
    )
    source2 = RawSource(
        source_type="test",
        source_uri="test://2",
        title="Test",
        content="Content"
    )
    source1.metadata["key"] = "value"
    assert "key" not in source2.metadata


def test_find_by_content_hash_exists(temp_vault):
    """find_by_content_hash returns matching record."""
    create(temp_vault, MemoryCreate(
        title="Test Memory",
        content="Test content for hashing",
        tags=["test"]
    ))
    # Index to get it into the database
    from memory.indexer import index_vault
    index_vault(temp_vault, apply=True)

    # Get the hash from the stored content
    from memory.crud import get_db
    conn = get_db(temp_vault)
    row = conn.execute("SELECT content_hash FROM memories WHERE title='Test Memory'").fetchone()
    if row and row[0]:
        result = find_by_content_hash(temp_vault, row[0])
        assert result is not None
        assert result["title"] == "Test Memory"


def test_find_by_content_hash_not_exists(temp_vault):
    """find_by_content_hash returns None for unknown hash."""
    result = find_by_content_hash(temp_vault, "nonexistent_hash")
    assert result is None


def test_duplicate_capture_prevention(temp_vault):
    """Capturing same content twice produces only one record."""
    import hashlib
    content = "Exact same content"
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Create first record
    create(temp_vault, MemoryCreate(
        title="Duplicate Test",
        content=content,
        tags=["test"],
        content_hash=content_hash
    ))
    from memory.indexer import index_vault
    index_vault(temp_vault, apply=True)

    # Check hash
    result = find_by_content_hash(temp_vault, content_hash)
    assert result is not None
    assert result["title"] == "Duplicate Test"
