"""Integration smoke test — full CLI workflow end-to-end via subprocess."""
import subprocess
import sys
import tempfile
from pathlib import Path

PYTHON = sys.executable


def _cli(*args: str, vault: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [str(PYTHON), "-m", "memory"]
    if vault:
        cmd += ["--vault", str(vault)]
    cmd += list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def test_smoke_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "test-vault"

        # 1. init
        r = _cli("init", str(vault))
        assert r.returncode == 0, f"init failed: {r.stderr}"
        assert (vault / "_index.md").exists()
        assert (vault / "data" / "memory.db").exists()

        # 2. capture
        raw_dir = vault / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        test_file = raw_dir / "rag-architecture.md"
        test_file.write_text("# RAG Architecture\n\nRAG combines retrieval with generation.")
        r = _cli("capture", "file", str(test_file), vault=vault)
        assert r.returncode == 0, f"capture failed: {r.stderr}"
        assert "Captured to" in r.stdout

        # 3. process
        r = _cli("process", "--dry-run", vault=vault)
        assert r.returncode == 0, f"process failed: {r.stderr}"
        assert "Processed:" in r.stdout or "No raw sources to process." in r.stdout

        # Actually process so we get notes for indexing
        r = _cli("process", vault=vault)
        assert r.returncode == 0, f"process apply failed: {r.stderr}"

        # 4. index
        r = _cli("index", "--dry-run", vault=vault)
        assert r.returncode == 0, f"index dry-run failed: {r.stderr}"
        assert "Not in DB" in r.stdout

        # Actually index
        r = _cli("index", "--apply", vault=vault)
        assert r.returncode == 0, f"index apply failed: {r.stderr}"
        assert "files" in r.stdout.lower() or "memories" in r.stdout.lower()

        # 5. search
        r = _cli("search", "RAG", vault=vault)
        assert r.returncode == 0, f"search failed: {r.stderr}"
        assert "Found" in r.stdout and "results" in r.stdout

        # 6. health
        r = _cli("health", vault=vault)
        assert r.returncode == 0, f"health failed: {r.stderr}"
        assert "Notes:" in r.stdout

        # 7. doctor
        r = _cli("doctor", vault=vault)
        assert r.returncode == 0, f"doctor failed: {r.stderr}"
        assert "No issues found" in r.stdout or "Issues found" in r.stdout
