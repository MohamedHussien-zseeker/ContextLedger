# AI Memory OS Roadmap

## v0.2 — Git for Memory

- Memory history — every change tracked with timestamp and author
- `memory log` — view change history
- `memory diff` — diff between two memory states
- `memory rollback` — revert to previous state
- Branch/experiment support — fork and merge memory

## v0.3 — Explainability

- `memory explain <query>` — explain what was retrieved and why
- Matched terms, relationship paths, scores per result
- Source document links on every memory
- Confidence scoring for retrieval relevance
- Stale/conflict markers for outdated memories

## v0.4 — Multi-Agent

- Shared memory API — unified read/write for all agents
- Claude, Codex, Gemini, Ollama integration examples
- Source, timestamp, confidence on every write
- `memory agents` — list active connections

## v0.5 — Memory Tests

- `memory test` — declarative retrieval assertions
- YAML test format: query + expected values
- CI/CD integration examples
- Duplicate detection and auto-merge

## v0.6 — Memory Replay

- `memory replay <project>` — timeline of knowledge evolution
- Decisions, architecture changes, linked commits
- Export replay as document
- Onboarding tool for new contributors
