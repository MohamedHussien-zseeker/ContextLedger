"""Tests for versioned database migrations."""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from memory.database import _local, get_db, init_db
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


# ── v3 history migration tests ──────────────────────────────────────


def test_v3_fresh_database(temp_vault):
    """Create new DB, run all migrations, verify v3 schema."""
    init_db(temp_vault)
    conn = get_db(temp_vault)

    # Verify deleted_at column exists
    cols = [row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()]
    assert "deleted_at" in cols

    # Verify memory_history table exists
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert "memory_history" in tables


def _setup_pre_v3_db(conn):
    """Create base schema and apply v1+v2 only, leaving v3 pending."""
    from memory.database import SCHEMA_SQL, TRIGGERS_SQL
    conn.executescript(SCHEMA_SQL)
    conn.executescript(TRIGGERS_SQL)
    conn.commit()
    # Apply v1 and v2 SQL directly (not via run_migrations which would also apply v3)
    migrations_dir = Path(__file__).resolve().parent.parent / "memory" / "migrations"
    for name in ("v1_add_helium_fields.sql", "v2_provenance_and_unique_hash.sql"):
        conn.executescript((migrations_dir / name).read_text())
    # Create migration tracking table and mark v1+v2 as applied
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version) VALUES ('v1_add_helium_fields'), ('v2_provenance_and_unique_hash')"
    )
    conn.commit()


def test_v3_upgrade_with_active_and_archived(temp_vault):
    """Insert active + archived memories, run v3, verify backfill."""
    conn = get_db(temp_vault)
    _setup_pre_v3_db(conn)

    # Insert test memories
    conn.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, archived, updated_at)
        VALUES ('active-1', 'note', 'Active Note', 'Content', 'draft', 1, 0, '2026-07-13T00:00:00Z')
    """)
    conn.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, archived, updated_at)
        VALUES ('archived-1', 'note', 'Archived Note', 'Content', 'draft', 1, 1, '2026-07-12T00:00:00Z')
    """)
    conn.commit()

    # Run v3 migration (v1/v2 already applied)
    applied = run_migrations(conn)
    assert "v3_history_table" in applied

    # Verify backfill
    history = conn.execute(
        "SELECT * FROM memory_history ORDER BY memory_id"
    ).fetchall()
    assert len(history) == 2

    # Active memory should have change_type='create'
    active_history = [h for h in history if h[1] == "active-1"][0]
    assert active_history[7] == "create"  # change_type column (index 7)

    # Archived memory should have change_type='delete'
    archived_history = [h for h in history if h[1] == "archived-1"][0]
    assert archived_history[7] == "delete"

    # Verify deleted_at set for archived
    archived_row = conn.execute(
        "SELECT deleted_at FROM memories WHERE id='archived-1'"
    ).fetchone()
    assert archived_row[0] is not None


def test_v3_json_tags_are_arrays(temp_vault):
    """Verify tags column produces JSON array, not escaped string."""
    conn = get_db(temp_vault)
    _setup_pre_v3_db(conn)

    # Insert memory with tags
    conn.execute("""
        INSERT INTO memories (id, type, title, content, status, importance, tags)
        VALUES ('tags-1', 'note', 'Tagged', 'Content', 'draft', 1, '["tag1", "tag2"]')
    """)
    conn.commit()

    run_migrations(conn)

    # Verify snapshot tags is JSON array
    snapshot = conn.execute(
        "SELECT snapshot FROM memory_history WHERE memory_id='tags-1'"
    ).fetchone()
    data = json.loads(snapshot[0])
    assert isinstance(data["tags"], list)
    assert data["tags"] == ["tag1", "tag2"]


def test_v3_idempotent(temp_vault):
    """Run migration twice, no errors, no duplicate history."""
    conn = get_db(temp_vault)
    _setup_pre_v3_db(conn)

    conn.execute("""
        INSERT INTO memories (id, type, title, content, status, importance)
        VALUES ('idem-1', 'note', 'Test', 'Content', 'draft', 1)
    """)
    conn.commit()

    # Run twice
    run_migrations(conn)
    count1 = conn.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]

    run_migrations(conn)
    count2 = conn.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]

    assert count1 == count2 == 1
