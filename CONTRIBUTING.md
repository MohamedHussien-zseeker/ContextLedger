# Contributing to ContextLedger

Thanks for your interest in improving ContextLedger.

## Development Setup

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
pip install -e .
```

## Running Tests

```bash
pytest -q
```

All 83 tests should pass before submitting a PR.

## Building the Demo

```bash
# Requires VHS and ttyd
docs/build-demo.sh
```

Generates `docs/demo.gif` and `docs/demo.mp4` from `docs/demo.tape`.

## Project Structure

```
memory/
├── cli.py          # CLI entry point
├── crud.py         # Database CRUD operations
├── database.py     # SQLite setup
├── doctor.py       # Vault diagnostics
├── entity.py       # Entity extraction
├── graph.py        # Knowledge graph
├── indexer.py      # Vault indexing
├── models.py       # Pydantic models
├── processor.py    # Source processing pipeline
├── search.py       # BM25 search
├── vault.py        # Vault initialization
├── api/            # FastAPI REST server
├── mcp/            # MCP stdio server
└── providers/      # Source capture providers
```

## How to Contribute

**Bug reports:** Use the [bug report template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=bug_report.md). Include steps to reproduce, expected behavior, and actual behavior.

**Feature requests:** Use the [feature request template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=feature_request.md). Explain the problem you're trying to solve.

**Install/first-run feedback:** Use the [feedback template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=feedback.md). Tell us what confused you.

**Code contributions:**

1. Fork the repo
2. Create a feature branch (`git checkout -b my-feature`)
3. Add tests for new functionality
4. Run `pytest -q` — all tests must pass
5. Submit a PR with a clear description of the change

## Release Checklist

Every release should include:

- [ ] All tests passing
- [ ] Demo updated if CLI changed
- [ ] Docs updated for new features
- [ ] CHANGELOG updated
- [ ] Version bumped in `pyproject.toml`
