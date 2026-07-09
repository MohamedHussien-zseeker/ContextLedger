"""Test semantic search graceful fallback (no Qdrant/Ollama)."""
from unittest.mock import patch
from memory import semantic


def test_qdrant_not_available():
    assert semantic.QDRANT_AVAILABLE is False


def test_get_client_returns_none_when_not_available():
    client = semantic.get_client()
    assert client is None


def test_ensure_collection_returns_false():
    result = semantic.ensure_collection()
    assert result is False


def test_index_memory_noop_when_no_qdrant():
    semantic.index_memory("test-id", "title", "content", ["tag1"])
    assert True


def test_semantic_search_returns_empty():
    results = semantic.semantic_search("test query")
    assert results == []


def test_embed_fallback_on_http_error():
    with patch("httpx.post", side_effect=Exception("connection refused")):
        emb = semantic._embed("test")
    assert len(emb) == semantic.config.EMBED_DIM
    assert all(v == 0.0 for v in emb)


def test_get_client_is_persistent():
    c1 = semantic.get_client()
    c2 = semantic.get_client()
    assert c1 is c2
