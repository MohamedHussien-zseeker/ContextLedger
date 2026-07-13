"""MCP server exposing memory tools to agents."""

import json
import os
import sys
from pathlib import Path

from memory.crud import create, get_stats
from memory.database import get_db, init_db
from memory.graph import health as graph_health
from memory.models import MemoryCreate
from memory.search import search
from memory.vault import default_vault_path

VAULT_PATH = Path(os.environ.get("MEMORY_VAULT", str(default_vault_path())))
READ_ONLY = os.environ.get("MEMORY_READ_ONLY", "0") == "1"


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
                "serverInfo": {"name": "contextledger", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    elif method == "tools/list":
        tools = [
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
                    "properties": {"limit": {"type": "integer", "default": 0}},
                },
            },
            {
                "name": "index_vault",
                "description": "Index vault into SQLite",
                "inputSchema": {
                    "type": "object",
                    "properties": {"apply": {"type": "boolean", "default": False}},
                },
            },
            {
                "name": "review_drafts",
                "description": "List drafts pending human review",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "generate_brief",
                "description": "Generate a project brief from approved knowledge",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string"},
                        "project_type": {"type": "string", "default": "landing-page"},
                    },
                    "required": ["project_name"],
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
        if READ_ONLY:
            tools = [t for t in tools if t["name"] not in {"capture_content", "process_sources", "index_vault"}]
        else:
            tools.extend(HISTORY_TOOLS)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tools},
        }
    elif method == "tools/call":
        tool = params.get("name", "")
        args = params.get("arguments", {})
        if READ_ONLY and tool in {"capture_content", "process_sources", "index_vault"}:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": "Helium MCP is read-only"},
            }
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
        elif tool == "review_drafts":
            from memory.review import list_pending

            text = json.dumps(list_pending(VAULT_PATH))
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}]}}
        elif tool == "generate_brief":
            from memory.brief import assemble_brief

            text = assemble_brief(VAULT_PATH, args["project_name"], args.get("project_type", "landing-page"))
            return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}]}}
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
                            "text": json.dumps({"id": mem.id, "title": mem.title}),
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
                                    "total_memories": stats.get("total_memories", 0),
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
                "result": {"content": [{"type": "text", "text": json.dumps(stats)}]},
            }
        elif tool == "memory_health":
            h = graph_health(VAULT_PATH)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": json.dumps(h)}]},
            }
        elif tool == "doctor":
            from memory.doctor import check

            result = check(VAULT_PATH)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]},
            }
        elif tool in {"list_memory_history", "diff_memory_history", "rollback_memory"}:
            result = handle_history_tools(tool, args, VAULT_PATH, READ_ONLY)
            if "error" in result:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": result["error"]["message"]},
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
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


HISTORY_TOOLS = [
    {
        "name": "list_memory_history",
        "description": "List history for a memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["memory_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diff_memory_history",
        "description": "Compare two versions of a memory",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "version_a": {"type": "integer", "minimum": 1},
                "version_b": {"type": "integer", "minimum": 1},
            },
            "required": ["memory_id", "version_a", "version_b"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rollback_memory",
        "description": "Rollback a memory to a previous version",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
                "target_version": {"type": "integer", "minimum": 1},
                "expected_version": {"type": "integer", "minimum": 1},
                "actor_type": {"type": "string", "enum": ["human", "agent", "system"]},
                "executed_by": {"type": "string", "minLength": 1},
                "initiated_by": {"type": "string"},
                "reason": {"type": "string"},
                "change_id": {"type": ["string", "null"]},
            },
            "required": ["memory_id", "target_version", "expected_version", "actor_type", "executed_by"],
            "additionalProperties": False,
        },
    },
]


def handle_history_tools(method: str, params: dict, vault_path: Path, read_only: bool) -> dict:
    """Handle history tool calls."""
    from memory.history import HistoryService, MemoryNotFoundError, VersionConflictError

    db = get_db(vault_path)
    service = HistoryService(db)

    if method == "list_memory_history":
        entries = service.get_log(
            memory_id=params["memory_id"],
            limit=params.get("limit", 50),
            offset=params.get("offset", 0),
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        [
                            {
                                "id": e.id,
                                "memory_id": e.memory_id,
                                "version": e.version,
                                "change_id": e.change_id,
                                "change_type": e.change_type,
                                "executed_by": e.executed_by,
                                "created_at": e.created_at,
                            }
                            for e in entries
                        ]
                    ),
                }
            ]
        }

    elif method == "diff_memory_history":
        diffs = service.diff_versions(
            params["memory_id"],
            params["version_a"],
            params["version_b"],
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        [
                            {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
                            for d in diffs
                        ]
                    ),
                }
            ]
        }

    elif method == "rollback_memory":
        if read_only:
            return {
                "error": {
                    "code": "read_only",
                    "message": "Rollback blocked in read-only mode",
                }
            }

        try:
            result = service.rollback(
                memory_id=params["memory_id"],
                target_version=params["target_version"],
                expected_version=params["expected_version"],
                actor_type=params["actor_type"],
                executed_by=params["executed_by"],
                initiated_by=params.get("initiated_by"),
                change_id=params.get("change_id"),
                reason=params.get("reason"),
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "changed": result.changed,
                                "entry": {
                                    "id": result.entry.id,
                                    "version": result.entry.version,
                                    "change_id": result.entry.change_id,
                                },
                            }
                        ),
                    }
                ]
            }
        except (MemoryNotFoundError, VersionConflictError) as e:
            return {
                "error": {
                    "code": "version_conflict" if isinstance(e, VersionConflictError) else "not_found",
                    "message": str(e),
                }
            }

    return {"error": {"code": -32601, "message": f"Unknown history tool: {method}"}}


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
