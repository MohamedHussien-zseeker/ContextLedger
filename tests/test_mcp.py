import json
import pytest
import tempfile
from pathlib import Path
from memory.database import _local
from memory.mcp.server import handle_request, VAULT_PATH


@pytest.fixture(autouse=True)
def clean_db():
    _local.conn = None
    yield
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def test_initialize(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(
            "memory.mcp.server.VAULT_PATH", Path(tmp)
        )
        # Reimport to pick up monkeypatched VAULT_PATH
        import importlib
        from memory.mcp import server
        importlib.reload(server)
        resp = server.handle_request({"method": "initialize", "id": 1})
        assert resp["result"]["serverInfo"]["name"] == "contextledger"
        assert resp["result"]["protocolVersion"] == "2024-11-05"


def test_tools_list():
    resp = handle_request({"method": "tools/list", "id": 2})
    assert "tools" in resp["result"]
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    assert "search_memories" in tool_names
    assert "capture_content" in tool_names
    assert "process_sources" in tool_names
    assert "index_vault" in tool_names
    assert "get_stats" in tool_names
    assert "memory_health" in tool_names
    assert "doctor" in tool_names


def test_unknown_method():
    resp = handle_request({"method": "unknown", "id": 3})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_unknown_tool():
    resp = handle_request(
        {"method": "tools/call", "params": {"name": "nonexistent"}, "id": 4}
    )
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_capture_and_search(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(
            "memory.mcp.server.VAULT_PATH", Path(tmp)
        )
        import importlib
        from memory.mcp import server
        importlib.reload(server)

        # Initialize DB first
        server.handle_request({"method": "initialize", "id": 1})

        # Capture content
        capt = server.handle_request(
            {
                "method": "tools/call",
                "params": {
                    "name": "capture_content",
                    "arguments": {
                        "title": "Test Memory",
                        "content": "Hello from MCP",
                        "tags": ["test", "mcp"],
                    },
                },
                "id": 5,
            }
        )
        assert "error" not in capt
        data = json.loads(capt["result"]["content"][0]["text"])
        assert data["title"] == "Test Memory"

        # Search for it
        srch = server.handle_request(
            {
                "method": "tools/call",
                "params": {
                    "name": "search_memories",
                    "arguments": {"query": "MCP", "limit": 10},
                },
                "id": 6,
            }
        )
        assert "error" not in srch
        results = json.loads(srch["result"]["content"][0]["text"])
        assert len(results) >= 1
        assert any(r["title"] == "Test Memory" for r in results)


def test_get_stats(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(
            "memory.mcp.server.VAULT_PATH", Path(tmp)
        )
        import importlib
        from memory.mcp import server
        importlib.reload(server)

        server.handle_request({"method": "initialize", "id": 1})
        resp = server.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "get_stats", "arguments": {}},
                "id": 7,
            }
        )
        assert "error" not in resp
        stats = json.loads(resp["result"]["content"][0]["text"])
        assert "total_memories" in stats
        assert stats["health"] == "ok"


def test_doctor(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(
            "memory.mcp.server.VAULT_PATH", Path(tmp)
        )
        import importlib
        from memory.mcp import server
        importlib.reload(server)

        server.handle_request({"method": "initialize", "id": 1})
        resp = server.handle_request(
            {
                "method": "tools/call",
                "params": {"name": "doctor", "arguments": {}},
                "id": 8,
            }
        )
        assert "error" not in resp
        result = json.loads(resp["result"]["content"][0]["text"])
        assert "healthy" in result
        assert "checks" in result
