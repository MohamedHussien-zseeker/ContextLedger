import json
import tempfile
from pathlib import Path

import pytest

from memory.database import _local
from memory.mcp.server import handle_history_tools, handle_request


@pytest.fixture(autouse=True)
def clean_db():
    _local.conn = None
    yield
    if _local.conn is not None:
        _local.conn.close()
        _local.conn = None


def test_initialize(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
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


def test_read_only_tools_hide_and_block_mutations(monkeypatch):
    from memory.mcp import server

    monkeypatch.setattr(server, "READ_ONLY", True)
    listed = server.handle_request({"method": "tools/list", "id": 20})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "search_memories" in names
    assert "generate_brief" in names
    assert not {"capture_content", "process_sources", "index_vault"} & names

    called = server.handle_request(
        {"method": "tools/call", "params": {"name": "capture_content", "arguments": {}}, "id": 21}
    )
    assert called["error"]["code"] == -32001


def test_unknown_method():
    resp = handle_request({"method": "unknown", "id": 3})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_unknown_tool():
    resp = handle_request({"method": "tools/call", "params": {"name": "nonexistent"}, "id": 4})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_capture_and_search(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
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
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
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
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
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


def _make_snapshot(title="Test", status="draft", tags=None, importance=1, deleted=False, content=None):
    """Create a valid snapshot for testing."""
    return {
        "schema_version": 1,
        "title": title,
        "content": content if content is not None else f"# {title}\n\nContent here.",
        "status": status,
        "tags": tags or [],
        "importance": importance,
        "vault_path": "vault/test",
        "deleted": deleted,
    }


def test_list_memory_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        monkeypatch.setattr(server, "VAULT_PATH", Path(tmp))
        server.handle_request({"method": "initialize", "id": 1})

        from memory.history import HistoryService

        service = HistoryService(server.get_db(Path(tmp)))
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(),
            actor_type="system",
            executed_by="test",
        )

        result = server.handle_history_tools(
            "list_memory_history",
            {"memory_id": "mem-1"},
            Path(tmp),
            read_only=False,
        )
        assert "content" in result
        entries = json.loads(result["content"][0]["text"])
        assert len(entries) == 1
        assert entries[0]["memory_id"] == "mem-1"
        assert entries[0]["version"] == 1


def test_diff_memory_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        monkeypatch.setattr(server, "VAULT_PATH", Path(tmp))
        server.handle_request({"method": "initialize", "id": 1})

        from memory.history import HistoryService

        service = HistoryService(server.get_db(Path(tmp)))
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="V1"),
            actor_type="system",
            executed_by="test",
        )
        service.update_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="V2"),
            expected_version=1,
            actor_type="system",
            executed_by="test",
        )

        result = server.handle_history_tools(
            "diff_memory_history",
            {"memory_id": "mem-1", "version_a": 1, "version_b": 2},
            Path(tmp),
            read_only=False,
        )
        assert "content" in result
        diffs = json.loads(result["content"][0]["text"])
        assert any(d["field"] == "title" for d in diffs)


def test_rollback_memory(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        monkeypatch.setattr(server, "VAULT_PATH", Path(tmp))
        server.handle_request({"method": "initialize", "id": 1})

        from memory.history import HistoryService

        service = HistoryService(server.get_db(Path(tmp)))
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="Original"),
            actor_type="system",
            executed_by="test",
        )
        service.update_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(title="Changed"),
            expected_version=1,
            actor_type="system",
            executed_by="test",
        )

        result = server.handle_history_tools(
            "rollback_memory",
            {
                "memory_id": "mem-1",
                "target_version": 1,
                "expected_version": 2,
                "actor_type": "system",
                "executed_by": "test",
                "reason": "Undo change",
            },
            Path(tmp),
            read_only=False,
        )
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert data["entry"]["version"] == 3


def test_rollback_blocked_in_read_only():
    result = handle_history_tools(
        "rollback_memory",
        {"memory_id": "mem-1", "target_version": 1, "expected_version": 1, "actor_type": "human", "executed_by": "test"},
        Path("/tmp/nonexistent"),
        read_only=True,
    )
    assert "error" in result
    assert result["error"]["code"] == "read_only"


def test_history_tools_in_tools_list(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        resp = server.handle_request({"method": "tools/list", "id": 2})
        tool_names = [t["name"] for t in resp["result"]["tools"]]
        assert "list_memory_history" in tool_names
        assert "diff_memory_history" in tool_names
        assert "rollback_memory" in tool_names


def test_history_tools_hidden_in_read_only(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        monkeypatch.setattr(server, "READ_ONLY", True)
        resp = server.handle_request({"method": "tools/list", "id": 2})
        tool_names = [t["name"] for t in resp["result"]["tools"]]
        assert "list_memory_history" not in tool_names
        assert "diff_memory_history" not in tool_names
        assert "rollback_memory" not in tool_names


def test_history_tools_via_mcp_call(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr("memory.mcp.server.VAULT_PATH", Path(tmp))
        import importlib
        from memory.mcp import server

        importlib.reload(server)
        monkeypatch.setattr(server, "VAULT_PATH", Path(tmp))
        server.handle_request({"method": "initialize", "id": 1})

        from memory.history import HistoryService

        service = HistoryService(server.get_db(Path(tmp)))
        service.create_memory(
            memory_id="mem-1",
            snapshot=_make_snapshot(),
            actor_type="system",
            executed_by="test",
        )

        resp = server.handle_request({
            "method": "tools/call",
            "params": {
                "name": "list_memory_history",
                "arguments": {"memory_id": "mem-1"},
            },
            "id": 10,
        })
        assert "error" not in resp
        entries = json.loads(resp["result"]["content"][0]["text"])
        assert len(entries) == 1
