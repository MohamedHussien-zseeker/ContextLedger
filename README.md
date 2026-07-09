# AI Memory OS

Local-first, human-editable memory infrastructure for AI agents. Think **Git for AI memory**: searchable, inspectable, versionable project knowledge that survives across sessions and assistants.

Turn raw sources into structured, linked, searchable knowledge. Not an agent — the memory layer agents use.

<!-- Demo GIF coming soon -->

![AI Memory OS Demo](docs/demo.gif)

## Why This Exists

AI sessions lose context after compaction. Project decisions scatter across chats, notes, and terminals. Agents need a shared memory layer with provenance, search, and human-editable files.

AI Memory OS solves this with a simple loop: **capture → process → link → index → search → serve**. Memory lives as Markdown you can edit, indexed in SQLite for fast search, and served through CLI, REST, or MCP for any agent to use.

## Roadmap

| Version | Milestone | Status |
|---------|-----------|--------|
| v0.1 | Core Memory — init, capture, process, index, search, health | **shipped** |
| v0.2 | Git for Memory — history, diff, rollback, branches | planned |
| v0.3 | Explainability — why a memory was retrieved, confidence scores | planned |
| v0.4 | Multi-Agent — shared memory across Claude, Codex, Gemini, Ollama | planned |
| v0.5 | Memory Tests — declarative assertions, CI/CD integration | planned |
| v0.6 | Memory Replay — timeline view of project knowledge evolution | planned |

## Quick Demo (5 minutes)

```bash
git clone <repo-url>
cd ai-memory-os
./install.sh

# Create a vault
memory init

# Capture a source file
memory capture file my-notes.md

# Process into linked knowledge notes
memory process

# Index into SQLite
memory index --apply

# Search with BM25 relevance scores
memory search "vector embeddings"

# Check graph health
memory health

# Diagnose issues
memory doctor
```

## Features

- **Human-editable memory** — Markdown files you can inspect, edit, and version
- **Knowledge graph** — wikilinks and hub MOCs with SQLite relationship tracking
- **BM25 full-text search** — SQLite FTS5 with relevance scoring
- **Provider system** — capture from files, URLs, or custom sources
- **Graph health metrics** — connectivity, isolated notes, component analysis
- **REST API** — FastAPI server at `127.0.0.1:9314`
- **MCP server** — stdio JSON-RPC for AI agent integration
- **Optional Qdrant** — semantic search via vector embeddings

## CLI Commands

| Command | Description |
|---------|-------------|
| `memory init [path]` | Create a new vault |
| `memory capture <scheme> <target>` | Capture a source via provider |
| `memory process` | Process raw sources into knowledge notes |
| `memory index --apply` | Index vault into SQLite |
| `memory search "query"` | Full-text search with BM25 scores |
| `memory health` | Graph connectivity report |
| `memory doctor` | Diagnose vault issues |
| `memory serve` | Start REST API server |
| `memory mcp` | Start MCP stdio server |

## Architecture

```
Knowledge Sources → Processing Pipeline → Human-Editable Memory → SQLite → Search/API/MCP → Agents
```

Vault structure:

```
vault/
├── raw/              # Captured sources
├── wiki/
│   ├── generated/    # Auto-generated knowledge notes
│   └── hubs/         # Topic hub MOCs
├── data/memory.db    # SQLite database
└── _index.md         # Vault root
```

## Requirements

- Python 3.11+
- SQLite with FTS5 support (included in Python's sqlite3 module)

## Install

```bash
./install.sh
```

Or manually:

```bash
pip install -e .
```

Optional semantic search:

```bash
pip install -e ".[qdrant]"
```

## Documentation

- [Quickstart](docs/quickstart.md) — step-by-step guide
- [Architecture](docs/architecture.md) — system design and data model
- [API Reference](docs/api.md) — REST endpoint documentation

## Comparison

| Feature | AI Memory OS | Obsidian | Vector DB | Agent Framework |
|---------|:---:|:---:|:---:|:---:|
| Human-editable memory | yes | yes | no | varies |
| Knowledge graph | yes | yes | no | varies |
| Agent-ready API/MCP | yes | no | partial | yes |
| Shared by multiple agents | yes | no | partial | partial |
| Optional semantic search | yes | no | yes | varies |
| Local-first | yes | yes | varies | varies |

## License

GPL-3.0
