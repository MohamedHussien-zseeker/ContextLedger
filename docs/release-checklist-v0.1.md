# v0.1 Release Checklist

## Pre-Release

- [ ] All 83+ tests pass: `pytest tests/ -v`
- [ ] Clean install from fresh venv: `pip install -e .`
- [ ] Full demo loop works: init → capture → process → index → search → health → doctor
- [ ] CLI `memory --help` shows all 9 commands
- [ ] README demo flow matches actual CLI behavior
- [ ] No hardcoded paths outside vault

## Code Quality

- [ ] No `print()` debug statements in library code
- [ ] No TODO/TBD placeholders in shipped modules
- [ ] All imports resolve (no missing dependencies)
- [ ] `pyproject.toml` version is `0.1.0`
- [ ] `.gitignore` covers `__pycache__/`, `*.egg-info/`, `data/`, `*.db`

## Documentation

- [ ] README has working 5-minute demo
- [ ] README lists all CLI commands
- [ ] README comparison table is accurate
- [ ] `docs/quickstart.md` matches README flow
- [ ] `docs/architecture.md` reflects current module structure
- [ ] `docs/api.md` documents all REST endpoints
- [ ] `docs/release-checklist-v0.1.md` exists (this file)

## Testing

- [ ] Unit tests: CRUD, search, processor, indexer, graph, vault, providers
- [ ] Integration: full loop from clean vault
- [ ] CLI: all subcommands dispatch correctly
- [ ] Search: BM25 scores returned for text queries
- [ ] Search: empty query returns results without scores
- [ ] Doctor: detects common issues

## Tag & Release

- [ ] Commit all changes
- [ ] Tag: `git tag v0.1.0`
- [ ] Push: `git push origin main --tags`
- [ ] Verify tag on GitHub: release page shows v0.1.0

## Post-Release

- [ ] Update vault project doc: `01-Projects/ai-memory-os/`
- [ ] Store memory: "AI Memory OS v0.1.0 released"
- [ ] Update brain.json project status
