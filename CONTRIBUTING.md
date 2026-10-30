# Contributing to ContextLedger

Thanks for your interest in improving ContextLedger. Bug reports, installation feedback, documentation fixes, and code contributions are all welcome.

## Development setup

```bash
git clone https://github.com/MohamedHussien-zseeker/ContextLedger.git
cd ContextLedger
pip install -e ".[dev]"
```

## Run the test suite

```bash
pytest -q
```

Run the full test suite before submitting a pull request. The expected test count can change as coverage grows; use the test runner's result rather than relying on a hard-coded count in this guide.

## Lint

If you have installed the development dependencies:

```bash
ruff check .
```

## Building the demo

The terminal demo is built with VHS and ttyd:

```bash
docs/build-demo.sh
```

This generates `docs/demo.gif` and `docs/demo.mp4` from `docs/demo.tape`.

## Project structure

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

## How to contribute

**Bug reports:** Use the [bug report template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=bug_report.md). Include steps to reproduce, expected behavior, and actual behavior.

**Feature requests:** Use the [feature request template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=feature_request.md). Explain the problem you're trying to solve.

**Install/first-run feedback:** Use the [feedback template](https://github.com/MohamedHussien-zseeker/ContextLedger/issues/new?template=feedback.md). Tell us what confused you, which operating system and Python version you use, and the command that failed.

**Code contributions:**

1. Fork the repository.
2. Create a feature branch (`git checkout -b my-feature`).
3. Add or update tests for changed behavior.
4. Run `pytest -q` and `ruff check .`.
5. Submit a pull request with a clear description and relevant test output.

## Pull request checklist

- [ ] The change addresses a clear problem or use case.
- [ ] Tests cover changed behavior.
- [ ] `pytest -q` passes.
- [ ] `ruff check .` passes, where applicable.
- [ ] Documentation is updated.
- [ ] The demo is updated if CLI behavior changes.
- [ ] Security-sensitive changes are called out in the PR description.

## Release checklist

Every release should include:

- [ ] All tests passing
- [ ] Demo updated if CLI changed
- [ ] Docs updated for new features
- [ ] Changelog updated
- [ ] Version bumped consistently in release metadata
