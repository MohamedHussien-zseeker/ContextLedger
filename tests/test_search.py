import tempfile
from pathlib import Path

import pytest

from memory.crud import create
from memory.database import _local, init_db
from memory.models import MemoryCreate
from memory.search import related, search


@pytest.fixture
def vault():
    _local.conn = None
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp)
        init_db(vp)
        create(
            vp,
            MemoryCreate(
                title="RAG Guide", content="RAG architecture with vector search", tags=["rag"]
            ),
        )
        create(
            vp,
            MemoryCreate(title="Agent Patterns", content="How to build AI agents", tags=["agents"]),
        )
        create(
            vp,
            MemoryCreate(
                title="Python Tips", content="Python 3.11 tips and tricks", tags=["python"]
            ),
        )
        yield vp
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def test_search_by_query(vault):
    results, total = search(vault, q="RAG")
    assert total >= 1
    assert any("RAG" in r.title for r in results)


def test_search_scores_populated(vault):
    results, _ = search(vault, q="RAG")
    assert len(results) >= 1
    assert all(r.score is not None for r in results)


def test_search_no_query_no_score(vault):
    results, total = search(vault)
    assert total >= 1
    assert all(r.score is None for r in results)


def test_search_by_tags(vault):
    results, total = search(vault, tags=["rag"])
    assert total >= 1


def test_search_limit(vault):
    results, total = search(vault, limit=1)
    assert len(results) == 1


def test_search_by_type(vault):
    results, total = search(vault, type_filter="note")
    assert total >= 1


def test_related_empty(vault):
    results, total = search(vault, q="RAG")
    if results:
        related_mems = related(vault, results[0].id)
        assert isinstance(related_mems, list)
