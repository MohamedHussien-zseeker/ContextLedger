"""Helium review, isolation, brief, and read-only retrieval tests."""

from pathlib import Path

from memory.brief import assemble_brief
from memory.database import get_db, init_db
from memory.indexer import index_vault
from memory.review import list_pending, transition
from memory.search import search


def _write(path: Path, status: str, stack: str, title: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntitle: {title}\nstatus: {status}\nstack: {stack}\n"
        "source_type: seed\nconfidentiality: confidential\n---\n\nUseful record.\n",
        encoding="utf-8",
    )


def test_database_connections_are_isolated_by_vault(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    init_db(first)
    get_db(first).execute("INSERT INTO memories (id, title) VALUES ('one', 'First')")
    get_db(first).commit()
    init_db(second)
    assert get_db(second).execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0
    assert get_db(first).execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_review_transition_and_approved_search(tmp_path):
    vault = tmp_path / "vault"
    init_db(vault)
    _write(vault / "drafts" / "taste.md", "draft", "core-stack", "Taste")
    index_vault(vault, apply=True)
    assert [item["id"] for item in list_pending(vault)] == ["taste"]
    assert search(vault, q="Useful")[1] == 0
    transition(vault, "taste", "approved")
    assert search(vault, q="Useful")[1] == 1


def test_brief_uses_only_approved_records(tmp_path):
    vault = tmp_path / "vault"
    _write(vault / "approved" / "core.md", "approved", "core-stack", "Core Tool")
    _write(vault / "drafts" / "draft.md", "draft", "core-stack", "Draft Tool")
    brief = assemble_brief(vault, "Test")
    assert "Core Tool" in brief
    assert "Draft Tool" not in brief
    assert "source: core" in brief


def test_supersede_links_old_record_to_approved_replacement(tmp_path):
    vault = tmp_path / "vault"
    init_db(vault)
    _write(vault / "approved" / "old.md", "approved", "core-stack", "Old")
    _write(vault / "drafts" / "new.md", "draft", "core-stack", "New")
    index_vault(vault, apply=True)
    transition(vault, "new", "approved")
    transition(vault, "old", "superseded", "new")
    old = (vault / "rejected" / "old.md").read_text()
    assert "status: superseded" in old
    assert "superseded_by: new" in old
    assert (vault / "approved" / "new.md").exists()
