# Architecture

ContextLedger is a local-first, human-editable memory system for AI agents. Data lives on disk as markdown files in an Obsidian-compatible vault, indexed into SQLite for fast search.

## Provider Pipeline

```
CLI / API / MCP
    │
    ▼
Capture Provider ─────► RawSource (Pydantic model)
    │                        │
    │                   ┌────┘
    ▼                   ▼
raw/ directory      processor.py
                        │
                    ┌───┴───┐
                    ▼       ▼
            wiki/generated/   wiki/hubs/
            (knowledge note)   (topic MOC)
```

- `CaptureProvider` is an abstract base class with a single `capture(target)` method returning a `RawSource` (title, content, metadata).
- Built-in providers: `file` (reads local files). Additional providers (YouTube, web, etc.) can be added by implementing the interface and registering in `providers/__init__.py`.
- Raw sources are written to `raw/` with YAML frontmatter tracking origin and capture timestamp.

## Processing Flow

1. **Capture** — a provider ingests a source and writes it to `raw/<slug>.md`.
2. **Process** — the processor reads each raw source, extracts keywords, classifies topic hubs, finds related notes via keyword overlap, and generates a knowledge note in `wiki/generated/<slug>.md`.
3. **Index** — the indexer scans the entire vault (skipping `.obsidian`, `.git`, etc.), parses frontmatter and wikilinks, upserts rows into SQLite, and rebuilds relationship edges.

## Data Model

### Vault (filesystem)

| Path | Purpose |
|------|---------|
| `_index.md` | Vault root index |
| `00-Inbox/` | Quick captures and bookmarks |
| `04-Knowledge/` | Reference knowledge |
| `raw/` | Source materials before processing |
| `wiki/generated/` | Auto-generated knowledge notes |
| `wiki/hubs/` | Topic hub MOCs |
| `data/memory.db` | SQLite database |

### SQLite Schema

```sql
memories (
    id          TEXT PRIMARY KEY,
    type        TEXT,       -- note, project, prompt, code, log, inbox
    title       TEXT,
    content     TEXT,
    source      TEXT,       -- obsidian, manual, etc.
    importance  INTEGER,
    tags        TEXT,       -- JSON array
    created_at  TEXT,
    updated_at  TEXT,
    accessed_at TEXT,
    access_count INTEGER,
    archived    INTEGER,
    vault_path  TEXT,
    embedding_id TEXT
);

memory_relationships (
    id               TEXT PRIMARY KEY,
    source_id        TEXT REFERENCES memories(id),
    target_id        TEXT REFERENCES memories(id),
    relationship_type TEXT,  -- wikilink, hub
    created_at       TEXT
);
```

Full-text search is backed by an FTS5 virtual table (`memories_fts`) kept in sync via triggers.

## CLI Design

Entry point: `memory.cli:main` registered via `pyproject.toml` `[project.scripts]`.

Commands are dispatched through argparse subparsers:

| Command | Function |
|---------|----------|
| `init` | Create a new vault |
| `capture` | Capture a source via a provider |
| `process` | Process raw sources into knowledge notes |
| `index` | Index vault into SQLite |
| `search` | Full-text search |
| `health` | Graph connectivity report |
| `doctor` | Diagnose vault issues |
| `serve` | Start REST API server |
| `mcp` | Start MCP stdio server |

## Optional Qdrant

When `qdrant-client` is installed (`pip install ai-memory-os[qdrant]`), semantic search becomes available via `memory/semantic.py`. Embeddings are generated through a local Ollama instance (`nomic-embed-text`, 768 dimensions) and stored in a Qdrant collection. The doctor command automatically checks Qdrant connectivity.

## API Server

FastAPI server listening on `127.0.0.1:9314` with bearer-token auth. See `docs/api.md`.

## MCP Server

A stdio-based JSON-RPC 2.0 MCP server exposing search, capture, process, index, stats, health, and doctor tools for AI agent integration.

## Graph Analysis

The `graph.py` module parses all markdown files, resolves `[[wikilinks]]` and markdown links, and builds an undirected graph to compute connectivity, isolated notes, and component sizes. This powers the `memory health` command.
