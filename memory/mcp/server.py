"""MCP server exposing memory tools to agents."""
import json
import sys
from pathlib import Path

from memory import config
from memory.vault import default_vault_path
from memory.database import init_db
from memory.crud import create, get, get_stats
from memory.models import MemoryCreate
from memory.search import search, related
from memory.graph import health as graph_health

VAULT_PATH = default_vault_path()


def handle_request(request: dict) -> dict:
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id", 0)
    if method == "initialize":
        init_db(VAULT_PATH)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "ai-memory-os", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "search_memories",
                        "description": "Search memories by keyword",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "limit": {"type": "integer", "default": 10},
                            },
                        },
                    },
                    {
                        "name": "capture_content",
                        "description": "Store a new memory",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title"],
                        },
                    },
                    {
                        "name": "process_sources",
                        "description": "Process raw sources into knowledge notes",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "limit": {"type": "integer", "default": 0}
                            },
                        },
                    },
                    {
                        "name": "index_vault",
                        "description": "Index vault into SQLite",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "apply": {"type": "boolean", "default": False}
                            },
                        },
                    },
                    {
                        "name": "get_stats",
                        "description": "Memory statistics",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "memory_health",
                        "description": "Graph connectivity health report",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                    {
                        "name": "doctor",
                        "description": "Diagnose vault issues",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ]
            },
        }
    elif method == "tools/call":
        tool = params.get("name", "")
        args = params.get("arguments", {})
        if tool == "search_memories":
            results, total = search(
                VAULT_PATH,
                q=args.get("query", ""),
                limit=args.get("limit", 10),
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                [
                                    {
                                        "id": m.id,
                                        "title": m.title,
                                        "type": m.type,
                                        "score": getattr(m, "score", None),
                                    }
                                    for m in results
                                ]
                            ),
                        }
                    ]
                },
            }
        elif tool == "capture_content":
            mem = create(
                VAULT_PATH,
                MemoryCreate(
                    title=args["title"],
                    content=args.get("content", ""),
                    tags=args.get("tags", []),
                ),
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {"id": mem.id, "title": mem.title}
                            ),
                        }
                    ]
                },
            }
        elif tool == "process_sources":
            from memory.processor import process_all

            results = process_all(VAULT_PATH, limit=args.get("limit", 0))
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                [
                                    {
                                        "source": r["source"],
                                        "action": r["action"],
                                        "hubs": r.get("hubs", []),
                                    }
                                    for r in results
                                ]
                            ),
                        }
                    ]
                },
            }
        elif tool == "index_vault":
            from memory.indexer import index_vault as do_index

            stats = do_index(VAULT_PATH, apply=args.get("apply", False))
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "files": stats["files"],
                                    "total_memories": stats.get(
                                        "total_memories", 0
                                    ),
                                }
                            ),
                        }
                    ]
                },
            }
        elif tool == "get_stats":
            stats = get_stats(VAULT_PATH)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(stats)}
                    ]
                },
            }
        elif tool == "memory_health":
            h = graph_health(VAULT_PATH)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(h)}
                    ]
                },
            }
        elif tool == "doctor":
            from memory.doctor import check

            result = check(VAULT_PATH)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result)}
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool}"},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main():
    init_db(VAULT_PATH)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": str(e)},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()


if __name__ == "__main__":
    main()
