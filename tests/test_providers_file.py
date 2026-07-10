import pytest

from memory.providers import get
from memory.providers.file import FileProvider


def test_file_provider_registered():
    assert get("file") is not None
    assert isinstance(get("file"), FileProvider)


def test_file_provider_capture(tmp_path):
    f = tmp_path / "hello-world.md"
    f.write_text("# Hello World\n\nThis is a test.")
    provider = get("file")
    rs = provider.capture(str(f))
    assert rs.source_type == "file"
    assert rs.title == "Hello World"
    assert "test" in rs.content


def test_file_provider_not_found():
    provider = get("file")
    with pytest.raises(FileNotFoundError):
        provider.capture("/nonexistent/file.md")
