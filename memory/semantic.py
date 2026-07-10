"""Optional Qdrant semantic search."""

import logging

from memory import config

_log = logging.getLogger("memory.semantic")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

_client = None


def get_client():
    global _client
    if not QDRANT_AVAILABLE:
        return None
    if _client is None:
        _client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
    return _client


def ensure_collection():
    client = get_client()
    if not client:
        return False
    try:
        client.get_collection(config.COLLECTION_NAME)
    except Exception:
        client.create_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=config.EMBED_DIM, distance=models.Distance.COSINE
            ),
        )
    return True


def _embed(text: str) -> list[float]:
    try:
        import httpx

        r = httpx.post(
            f"{config.OLLAMA_HOST}/api/embeddings",
            json={"model": config.EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        return r.json().get("embedding", [0.0] * config.EMBED_DIM)
    except Exception as e:
        _log.warning("embedding_failed: %s", e)
        return [0.0] * config.EMBED_DIM


def index_memory(memory_id: str, title: str, content: str, tags: list[str]):
    client = get_client()
    if not client:
        return
    text = f"{title}\n{content}"
    vector = _embed(text)
    client.upsert(
        collection_name=config.COLLECTION_NAME,
        points=[
            models.PointStruct(id=memory_id, vector=vector, payload={"title": title, "tags": tags})
        ],
    )


def semantic_search(query: str, limit: int = 10) -> list:
    client = get_client()
    if not client:
        return []
    vector = _embed(query)
    hits = client.search(
        collection_name=config.COLLECTION_NAME,
        query_vector=vector,
        limit=limit,
    )
    from memory.crud import get as get_memory

    results = []
    for hit in hits:
        mem = get_memory(config.DEFAULT_VAULT, hit.id)
        if mem:
            mem.score = hit.score
            results.append(mem)
    return results
