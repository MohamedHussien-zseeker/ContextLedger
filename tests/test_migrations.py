"""Tests for versioned database migrations."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from memory.database import init_db, get_db, _local
from memory.migrations.runner import get_applied, get_pending, run_migrations


@pytest.fixture
def temp_vault():
    """Create a temporary vault directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "test-vault"
        vault_path.mkdir()
        # Reset thread-local connection for clean state
        _local.conn = None
        yield vault_path
        _local.conn = None


def test_clean_install_migrations(temp_vault):
    """Migrations run on a fresh database."""
    init_db(temp_vault)
    conn = get_db(temp_vault)

    applied = get_applied(conn)
    assert "v1_add_helium_fields" in applied

    # Verify new columns exist
    cursor = conn.execute("PRAGMA table_info(memories)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "status" in columns
    assert "content_hash" in columns
    assert "source_type" in columns
    assert "captured_at" in columns
    assert "confidentiality" in columns


def test_idempotent_migrations(temp_vault):
    """Running migrations twice does not fail."""
    init_db(temp_vault)
    conn = get_db(temp_vault)

    # Run again
    applied = run_migrations(conn)
    assert applied == []  # Nothing new applied

    # Verify columns still exist
    cursor = conn.execute("PRAGMA table_info(memories)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "status" in columns


def test_pending_migrations(temp_vault):
    """Pending migrations are reported correctly."""
    # Before init
    vault_db = temp_vault / "data"
    vault_db.mkdir()
    conn = sqlite3.connect(str(vault_db / "memory.db"))
    conn.row_factory = sqlite3.Row

    pending = get_pending(conn)
    assert "v1_add_helium_fields" in pending

    # After init
    conn.close()
    init_db(temp_vault)
    conn = get_db(temp_vault)

    pending = get_pending(conn)
    assert len(pending) == 0


def test_upgrade_from_bare_schema(temp_vault):
    """Upgrade path from schema without migration tracking."""
    conn = get_db(temp_vault)

    # Create base schema manually (simulating pre-migration database)
    from memory.database import SCHEMA_SQL, TRIGGERS_SQL
    conn.executescript(SCHEMA_SQL)
    conn.executescript(TRIGGERS_SQL)
    conn.commit()

    # Now run migrations
    applied = run_migrations(conn)
    assert "v1_add_helium_fields" in applied

    # Verify new columns
    cursor = conn.execute("PRAGMA table_info(memories)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "status" in columns
    assert "content_hash" in columns


def test_default_status_value(temp_vault):
    """New memories get status='approved' by default."""
    init_db(temp_vault)
    conn = get_db(temp_vault)

    conn.execute("""
        INSERT INTO memories (id, title, content, vault_path)
        VALUES ('test-1', 'Test', 'Content', 'raw/test.md')
    """)
    conn.commit()

    row = conn.execute("SELECT status FROM memories WHERE id = 'test-1'").fetchone()
    assert row[0] == "approved"


def test_default_confidentiality_value(temp_vault):
    """New memories get confidentiality='confidential' by default."""
    init_db(temp_vault)
    conn = get_db(temp_vault)

    conn.execute("""
        INSERT INTO memories (id, title, content, vault_path)
        VALUES ('test-2', 'Test', 'Content', 'raw/test.md')
    """)
    conn.commit()

    row = conn.execute("SELECT confidentiality FROM memories WHERE id = 'test-2'").fetchone()
    assert row[0] == "confidential"
