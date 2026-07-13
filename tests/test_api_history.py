"""Tests for the history REST API endpoints."""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_VAULT = Path(tempfile.mkdtemp())
os.environ["MEMORY_VAULT"] = str(TEST_VAULT)

from memory.api.server import VAULT_PATH, app  # noqa: E402
from memory.database import get_db, init_db  # noqa: E402
from memory.history import HistoryService  # noqa: E402

init_db(VAULT_PATH)


def _make_snapshot(title="Test", content="Content", status="approved"):
    return {
        "schema_version": 1,
        "title": title,
        "content": content,
        "status": status,
        "tags": ["test"],
        "importance": 3,
        "vault_path": "notes/test.md",
        "deleted": False,
    }


@pytest.fixture(autouse=True)
def clear_db():
    yield
    db = get_db(VAULT_PATH)
    db.execute("DELETE FROM memory_history")
    db.execute("DELETE FROM memory_relationships")
    db.execute("DELETE FROM memories")
    db.commit()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def service():
    db = get_db(VAULT_PATH)
    return HistoryService(db)


def test_list_history(client, service):
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )

    response = client.get("/v1/memories/mem-1/history")
    assert response.status_code == 200
    data = response.json()
    assert "entries" in data
    assert len(data["entries"]) == 1


def test_diff_history(client, service):
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V1"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )

    service.update_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V2"),
        expected_version=1,
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )

    response = client.get("/v1/memories/mem-1/history/diff?a=1&b=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0


def test_rollback_history(client, service):
    service.create_memory(
        memory_id="mem-1",
        snapshot=_make_snapshot(title="V1"),
        actor_type="human",
        executed_by="zserverai",
        initiated_by="zserverai",
    )

    response = client.post(
        "/v1/memories/mem-1/history/rollback",
        json={
            "target_version": 1,
            "expected_version": 1,
            "actor_type": "human",
            "executed_by": "zserverai",
            "initiated_by": "zserverai",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["changed"] is True
