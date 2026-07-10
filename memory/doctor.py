"""Diagnose vault health."""

from pathlib import Path

from memory import config


def check(vault_path: Path) -> dict:
    issues = []
    checks = {}
    checks["vault_exists"] = vault_path.exists()
    if not vault_path.exists():
        issues.append("Vault directory not found")
        return {"healthy": False, "issues": issues, "checks": checks}
    checks["index_md"] = (vault_path / "_index.md").exists()
    if not checks["index_md"]:
        issues.append("Missing _index.md")
    checks["raw_dir"] = (vault_path / config.RAW_DIR).exists()
    checks["db_exists"] = (vault_path / "data/memory.db").exists()
    if not checks["db_exists"]:
        issues.append("Missing data/memory.db — run 'memory index'")
    else:
        from memory.database import get_db

        try:
            db = get_db(vault_path)
            db.execute("SELECT 1").fetchone()
            count = db.execute("SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0]
            checks["memory_count"] = count
        except Exception as e:
            checks["db_error"] = str(e)
            issues.append(f"SQLite error: {e}")
    if config.QDRANT_HOST:
        try:
            import httpx

            r = httpx.get(f"http://{config.QDRANT_HOST}:{config.QDRANT_PORT}/", timeout=2)
            checks["qdrant"] = r.status_code == 200
        except Exception:
            checks["qdrant"] = False
    return {"healthy": len(issues) == 0, "issues": issues, "checks": checks}
