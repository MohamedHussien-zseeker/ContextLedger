import tempfile
from pathlib import Path

import pytest

from memory.database import _local
from memory.indexer import (
    extract_tags,
    extract_title,
    index_vault,
    iter_markdown_files,
    path_to_type,
)
from memory.vault import init_vault


@pytest.fixture(autouse=True)
def reset_db():
    _local.conn = None
    yield
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def test_path_to_type():
    assert path_to_type("01-Projects/test.md") == "project"
    assert path_to_type("04-Knowledge/test.md") == "note"
    assert path_to_type("wiki/generated/test.md") == "note"


def test_extract_title():
    assert extract_title("# Hello\nWorld", None, "file.md") == "Hello"
    assert extract_title("No heading", None, "my-note.md") == "My Note"


def test_extract_tags():
    assert extract_tags({"tags": ["a", "b"]}) == ["a", "b"]
    assert extract_tags({"hubs": ["RAG"]}) == ["RAG"]


def test_iter_markdown_files():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        (vp / "04-Knowledge/test-note.md").write_text("# Test")
        files = iter_markdown_files(vp)
        assert any("test-note.md" in f for f in files)


def test_index_vault_dry_run():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        (vp / "04-Knowledge/test.md").write_text(
            "---\ntags: [test]\n---\n# Test Note\nContent here."
        )
        stats = index_vault(vp, apply=False)
        assert stats["files"] >= 1
        for r in stats["results"]:
            assert r["action"] == "dry-run"
