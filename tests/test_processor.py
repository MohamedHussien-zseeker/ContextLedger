import pytest
import tempfile
from pathlib import Path
from memory.processor import (
    slugify, title_from_body, choose_hubs, keywords,
    parse_frontmatter, dump_frontmatter, plain_lines,
    process_source, process_all, process,
)
from memory.vault import init_vault
from memory.providers.base import RawSource


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("RAG Architecture") == "rag-architecture"


def test_title_from_body():
    assert title_from_body("# Hello\nWorld", "fallback") == "Hello"
    assert title_from_body("no heading", "fallback") == "Fallback"


def test_choose_hubs():
    hubs = choose_hubs("rag vector search embedding qdrant")
    assert "RAG" in hubs


def test_keywords():
    kw = keywords("agent automation workflow harness")
    assert "agent" in kw
    assert "the" not in kw


def test_parse_frontmatter():
    text = "---\ntitle: Test\ntags: [a, b]\n---\nBody"
    fm, body = parse_frontmatter(text)
    assert fm["title"] == "Test"
    assert body == "Body"


def test_parse_frontmatter_none():
    fm, body = parse_frontmatter("Just text")
    assert fm == {}
    assert body == "Just text"


def test_dump_and_parse_roundtrip():
    fm = {"title": "Test", "tags": ["a", "b"], "count": 3}
    body = "Hello"
    text = dump_frontmatter(fm) + body
    parsed_fm, parsed_body = parse_frontmatter(text)
    assert parsed_fm["title"] == "Test"
    assert parsed_body == "Hello"


def test_plain_lines():
    body = "# Heading\n\nSome longer content that should be included.\n- A bullet\n\n```\ncode block\n```"
    lines = plain_lines(body)
    assert len(lines) >= 1


def test_process_source(vault_fixture):
    vault_path, raw_file = vault_fixture
    result = process_source(vault_path, raw_file, dry_run=True)
    assert result["action"] in ("write", "skip")


def test_process_all(vault_fixture):
    vault_path, raw_file = vault_fixture
    results = process_all(vault_path, dry_run=True)
    assert len(results) >= 1
    assert results[0]["action"] in ("write", "skip")


def test_process_with_rawsource(vault_fixture):
    vault_path, _ = vault_fixture
    rs = RawSource(
        source_type="test",
        source_uri="test://example",
        title="Test Source",
        content="# Test Source\n\nContent about RAG and vector search.",
    )
    result = process(vault_path, rs, dry_run=True)
    assert result["action"] in ("write", "skip")


@pytest.fixture
def vault_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        raw_dir = vp / "raw"
        raw_dir.mkdir(exist_ok=True)
        raw_file = raw_dir / "test-source.md"
        raw_file.write_text("---\ntags: [test]\n---\n# Test Source\n\nThis is a markdown note about RAG architecture and vector search.")
        yield vp, raw_file
