# ContextLedger

**Git for AI memory.**

GPL-3.0 licensed. Python 3.11+. 83 tests passing. CLI, REST API, and MCP server included.

[![Tests](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/tests.yml/badge.svg)](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/tests.yml)
[![CodeQL](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/codeql.yml/badge.svg)](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/codeql.yml)
[![Lint](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/lint.yml/badge.svg)](https://github.com/MohamedHussien-zseeker/ContextLedger/actions/workflows/lint.yml)

Local-first, human-editable memory infrastructure for AI agents. Searchable, inspectable, versionable project knowledge that survives across sessions and assistants.

> ContextLedger is an implementation of the [AI Memory OS](docs/architecture.md) architecture.

![ContextLedger Demo](docs/demo.gif)

*What you just saw: init a vault, capture a source, process into linked knowledge, index into SQLite, search with BM25 scores, check graph health, diagnose issues — 7 commands, 30 seconds, zero cloud.*

## Quick Install

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
./install.sh
```

## 30-Second Demo

```bash
memory init /tmp/my-vault
memory --vault /tmp/my-vault capture file my-notes.md
memory --vault /tmp/my-vault process
memory --vault /tmp/my-vault index --apply
memory --vault /tmp/my-vault search "your query"
memory --vault /tmp/my-vault health
memory --vault /tmp/my-vault doctor
```

## Why ContextLedger

AI sessions lose context after compaction. Project decisions scatter across chats, notes, and terminals. Agents retrieve context without explaining where it came from.

**The problem:**
- Sessions forget project state after compaction
- Docs drift from what's actually deployed
- Agents can't explain why they retrieved specific context
- Memory is locked in proprietary formats or cloud services

**ContextLedger solves this** with a simple loop: **capture → process → link → index → search → serve**. Memory lives as Markdown you can edit, indexed in SQLite for fast search, and served through CLI, REST, or MCP for any agent to use.

Not an agent — the memory layer agents use.

## Current Release

**v0.1.0** — first working release.

| Capability | Status |
|------------|--------|
| Vault init | working |
| Source capture (file) | working |
| Processing pipeline | working |
| Knowledge graph (wikilinks, MOCs) | working |
| SQLite + FTS5 indexing | working |
| BM25 search with scores | working |
| Graph health metrics | working |
| REST API (FastAPI) | working |
| MCP server (stdio) | working |
| 83 tests passing | verified |

**Next:** v0.2 adds Git-backed memory history and drift checks.

## Integration Surface

ContextLedger provides four ways to access memory:

| Interface | For | Protocol |
|-----------|-----|----------|
| **CLI** | Humans, scripts | `memory` command |
| **REST API** | Apps, gateways | HTTP, bound to localhost (`127.0.0.1:9314`) |
| **MCP server** | AI agents | stdio JSON-RPC |
| **Markdown vault** | Obsidian, manual editing | Files on disk |

Any agent that speaks MCP or HTTP can use ContextLedger as its memory layer.

## Features

- **Human-editable memory** — Markdown files you can inspect, edit, and version
- **Knowledge graph** — wikilinks and hub MOCs with SQLite relationship tracking
- **BM25 full-text search** — SQLite FTS5 with relevance scoring
- **Provider system** — extensible capture (file provider, custom sources)
- **Graph health metrics** — connectivity, isolated notes, component analysis
- **REST API** — FastAPI server bound to localhost by default (`127.0.0.1:9314`)
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

## Roadmap

| Version | Focus | Status |
|---------|-------|--------|
| **v0.1.0** | Core loop: capture, process, index, search, serve | released |
| **v0.2** | Git-backed memory history and drift checks | planned |
| **v0.3** | Retrieval explainability and provenance | planned |

Every release includes tests, demo updates, and docs updates.

## Comparison

| Feature | ContextLedger | Obsidian | Vector DB | Agent Framework |
|---------|:---:|:---:|:---:|:---:|
| Human-editable memory | yes | yes | no | varies |
| Knowledge graph | yes | yes | no | varies |
| Agent-ready API/MCP | yes | no | partial | yes |
| Shared by multiple agents | agent-ready (MCP/API) | no | partial | partial |
| Optional semantic search | yes | no | yes | varies |
| Local-first | yes | yes | varies | varies |

## Testing

```bash
pytest -q
```

83 tests covering CLI, API, MCP, search, graph, processor, and integration.

## Documentation

- [Quickstart](docs/quickstart.md) — step-by-step guide
- [Architecture](docs/architecture.md) — system design and data model
- [API Reference](docs/api.md) — REST endpoint documentation
- [Contributing](CONTRIBUTING.md) — development setup and guidelines

## Requirements

- Python 3.11+
- SQLite with FTS5 support (included in Python's sqlite3 module)

## License

GPL-3.0
