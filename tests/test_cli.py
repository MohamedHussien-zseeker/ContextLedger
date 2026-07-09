"""Tests for the CLI dispatch."""
import argparse
import pytest
import tempfile
from pathlib import Path
from memory.database import _local
from memory.vault import init_vault
from memory.cli import cmd_init, cmd_health, cmd_doctor, cmd_search, cmd_index, cmd_process


# ── Helpers ──────────────────────────────────────────────────────────────

def _vault():
    _local.conn = None
    tmp = tempfile.TemporaryDirectory()
    vp = Path(tmp.name) / "test-vault"
    init_vault(vp)
    return vp, tmp


def _ns(**kwargs):
    return argparse.Namespace(**kwargs)


@pytest.fixture(autouse=True)
def reset_db():
    _local.conn = None
    yield
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


# ── init ─────────────────────────────────────────────────────────────────

def test_cmd_init_creates_vault():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "new-vault"
        args = _ns(path=str(p), vault=None)
        cmd_init(args)
        assert (p / "_index.md").exists()
        assert (p / "data/memory.db").exists()


def test_cmd_init_default_path(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.config.CONFIG_DIR", Path(tmp))
        args = _ns(path=None, vault=None)
        cmd_init(args)
        vault_path = Path(tmp) / "vault"
        assert vault_path.exists()


def test_cmd_init_existing_raises():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "_index.md").write_text("")
        args = _ns(path=str(p), vault=None)
        with pytest.raises(SystemExit):
            cmd_init(args)


# ── health ───────────────────────────────────────────────────────────────

def test_cmd_health(capsys):
    vp, tmp = _vault()
    args = _ns(vault=vp)
    (vp / "04-Knowledge/test.md").write_text("# Test Note\n[[other]]")
    cmd_health(args)
    captured = capsys.readouterr().out
    assert "Notes:" in captured
    assert "Connected:" in captured
    tmp.cleanup()


# ── doctor ───────────────────────────────────────────────────────────────

def test_cmd_doctor_no_vault(capsys):
    args = _ns(vault=Path("/nonexistent/vault/path"))
    with pytest.raises(SystemExit):
        cmd_doctor(args)


def test_cmd_doctor_ok(capsys):
    vp, tmp = _vault()
    args = _ns(vault=vp)
    cmd_doctor(args)
    captured = capsys.readouterr().out
    assert "No issues found" in captured
    tmp.cleanup()


# ── index (dry-run) ──────────────────────────────────────────────────────

def test_cmd_index_dry_run(capsys):
    vp, tmp = _vault()
    (vp / "04-Knowledge/test.md").write_text("---\ntags: [test]\n---\n# Test Note\nHello.")
    args = _ns(vault=vp, apply=False, dry_run=True)
    cmd_index(args)
    captured = capsys.readouterr().out
    assert "Files:" in captured
    assert "Not in DB:" in captured
    tmp.cleanup()


# ── process (dry-run) ────────────────────────────────────────────────────

def test_cmd_process_dry_run(capsys):
    vp, tmp = _vault()
    (vp / "raw" / "test-source.md").write_text("# Test Source\nContent about RAG and memory systems.")
    args = _ns(vault=vp, force=False, dry_run=True, limit=0)
    cmd_process(args)
    captured = capsys.readouterr().out
    assert "Processed:" in captured or "No raw sources to process." in captured
    tmp.cleanup()


# ── search ───────────────────────────────────────────────────────────────

def test_cmd_search_empty(capsys):
    vp, tmp = _vault()
    args = _ns(vault=vp, query="nothing", limit=10)
    cmd_search(args)
    captured = capsys.readouterr().out
    assert "Found 0 results" in captured
    tmp.cleanup()
