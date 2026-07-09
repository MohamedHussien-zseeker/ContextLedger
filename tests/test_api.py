"""Tests for the REST API server."""
import os
import tempfile
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_VAULT = Path(tempfile.mkdtemp())
os.environ["MEMORY_VAULT"] = str(TEST_VAULT)

from memory.api.server import app
from memory.database import init_db, get_db

init_db(TEST_VAULT)


def _clean_raw_dir():
    raw_dir = TEST_VAULT / "raw"
    if raw_dir.exists():
        for f in list(raw_dir.iterdir()):
            if f.is_file():
                f.unlink()


def _clean_wiki_dirs():
    for sub in ("generated", "hubs"):
        d = TEST_VAULT / "wiki" / sub
        if d.exists():
            for f in list(d.iterdir()):
                if f.is_file():
                    f.unlink()


@pytest.fixture(autouse=True)
def clear_db():
    yield
    db = get_db(TEST_VAULT)
    db.execute("DELETE FROM memory_relationships")
    db.execute("DELETE FROM memories")
    db.commit()
    _clean_raw_dir()
    _clean_wiki_dirs()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "memory_count" in data


def test_create_memory(client):
    resp = client.post("/v1/remember", json={
        "title": "Test Memory",
        "content": "This is a test content",
        "type": "note",
        "tags": ["test", "api"],
        "importance": 3,
        "source": "api-test",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Memory"
    assert data["content"] == "This is a test content"
    assert data["type"] == "note"
    assert data["tags"] == ["test", "api"]
    assert data["importance"] == 3
    assert data["source"] == "api-test"
    assert "id" in data
    assert not data["archived"]


def test_get_memory(client):
    create_resp = client.post("/v1/remember", json={"title": "Get Test"})
    mem_id = create_resp.json()["id"]

    resp = client.get(f"/v1/memories/{mem_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == mem_id
    assert resp.json()["title"] == "Get Test"


def test_get_memory_not_found(client):
    resp = client.get("/v1/memories/nonexistent-id")
    assert resp.status_code == 404


def test_update_memory(client):
    create_resp = client.post("/v1/remember", json={
        "title": "Original Title",
        "content": "Original content",
    })
    mem_id = create_resp.json()["id"]

    resp = client.put(f"/v1/memories/{mem_id}", json={
        "title": "Updated Title",
        "content": "Updated content",
        "importance": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated Title"
    assert data["content"] == "Updated content"
    assert data["importance"] == 5


def test_update_memory_not_found(client):
    resp = client.put("/v1/memories/nonexistent", json={"title": "Nope"})
    assert resp.status_code == 404


def test_delete_memory(client):
    create_resp = client.post("/v1/remember", json={"title": "To Delete"})
    mem_id = create_resp.json()["id"]

    resp = client.delete(f"/v1/memories/{mem_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    assert resp.json()["id"] == mem_id

    resp = client.get(f"/v1/memories/{mem_id}")
    assert resp.status_code == 404


def test_delete_memory_not_found(client):
    resp = client.delete("/v1/memories/nonexistent")
    assert resp.status_code == 404


def test_search_by_query(client):
    client.post("/v1/remember", json={"title": "Python Programming", "content": "Learning Python basics"})
    client.post("/v1/remember", json={"title": "Java Programming", "content": "Java is also nice"})

    resp = client.post("/v1/search", json={"q": "Python"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    titles = [m["title"] for m in data["memories"]]
    assert "Python Programming" in titles


def test_search_by_tags(client):
    client.post("/v1/remember", json={"title": "Tagged A", "tags": ["alpha", "common"]})
    client.post("/v1/remember", json={"title": "Tagged B", "tags": ["beta", "common"]})

    resp = client.post("/v1/search", json={"tags": ["alpha"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(m["title"] == "Tagged A" for m in data["memories"])


def test_search_pagination(client):
    for i in range(5):
        client.post("/v1/remember", json={"title": f"Page Item {i}", "tags": ["pagination"]})

    resp = client.post("/v1/search", json={"tags": ["pagination"], "limit": 2, "offset": 0})
    assert resp.status_code == 200
    assert len(resp.json()["memories"]) == 2


def test_stats(client):
    client.post("/v1/remember", json={"title": "Stats Note", "type": "note", "source": "test"})
    client.post("/v1/remember", json={"title": "Stats Project", "type": "project", "source": "test"})

    resp = client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_memories"] >= 2
    assert "by_type" in data
    assert "by_source" in data
    assert data["health"] == "ok"


def test_capture_invalid_provider(client):
    resp = client.post("/v1/capture", json={
        "scheme": "nosuchprovider",
        "target": "anything",
    })
    assert resp.status_code == 400


def test_capture_file(client):
    src_file = TEST_VAULT / "test_capture_source.txt"
    src_file.write_text("Hello from capture test")
    resp = client.post("/v1/capture", json={
        "scheme": "file",
        "target": str(src_file),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Capture Source"
    assert not data["processed"]
    raw_path = TEST_VAULT / data["source"]
    assert raw_path.exists()


def test_process_no_sources(client):
    _clean_raw_dir()
    resp = client.post("/v1/process", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


def test_index(client):
    note = TEST_VAULT / "test-note.md"
    note.write_text("---\ntitle: Test Index Note\ntags: [test]\n---\n\n# Test Index Note\n\nSome content.")
    resp = client.post("/v1/index", json={"apply": True})
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    assert data["total_memories"] >= 1
    note.unlink()


def test_entities(client):
    create_resp = client.post("/v1/remember", json={
        "title": "Entity Test about AI and Python",
        "content": "Check https://example.com for more info",
    })
    mem_id = create_resp.json()["id"]

    resp = client.get(f"/v1/entities/{mem_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["memory_id"] == mem_id
    assert "urls" in data
    assert "https://example.com" in data["urls"]


def test_entities_not_found(client):
    resp = client.get("/v1/entities/nonexistent")
    assert resp.status_code == 404


def test_related(client):
    create_resp = client.post("/v1/remember", json={"title": "Related Source"})
    source_id = create_resp.json()["id"]
    create_resp = client.post("/v1/remember", json={"title": "Related Target"})
    target_id = create_resp.json()["id"]

    db = get_db(TEST_VAULT)
    db.execute(
        "INSERT INTO memory_relationships (id, source_id, target_id, relationship_type) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), source_id, target_id, "wikilink"),
    )
    db.commit()

    resp = client.get(f"/v1/related/{source_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["memories"]) >= 1
