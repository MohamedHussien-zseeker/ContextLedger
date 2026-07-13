"""Migration runner for ContextLedger."""
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent


def get_applied(conn: sqlite3.Connection) -> set:
    """Get set of applied migration versions."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.commit()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def get_pending(conn: sqlite3.Connection) -> list[str]:
    """Get list of pending migration versions in order."""
    applied = get_applied(conn)
    migration_files = sorted(MIGRATIONS_DIR.glob("v*.sql"))
    return [mf.stem for mf in migration_files if mf.stem not in applied]


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Run all pending migrations. Returns list of applied versions.

    Each migration runs as a single transactional script with BEGIN IMMEDIATE
    to ensure atomicity — the migration DDL/DML and the schema_migrations
    insert either both succeed or both roll back.
    """
    applied = get_applied(conn)
    migration_files = sorted(MIGRATIONS_DIR.glob("v*.sql"))
    applied_now = []

    for mf in migration_files:
        version = mf.stem
        if version not in applied:
            sql = mf.read_text()
            version_sql = version.replace("'", "''")
            script = f"""
BEGIN IMMEDIATE;
{sql}
INSERT INTO schema_migrations (version)
VALUES ('{version_sql}');
COMMIT;
"""
            try:
                conn.executescript(script)
            except Exception:
                conn.rollback()
                raise
            applied_now.append(version)

    return applied_now
