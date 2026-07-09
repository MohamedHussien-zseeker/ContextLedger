import pytest
import tempfile
from pathlib import Path
from memory.vault import init_vault


def test_init_vault_creates_structure():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test-vault"
        result = init_vault(path)
        assert result == path
        assert (path / "_index.md").exists()
        assert (path / "raw").exists()
        assert (path / "wiki/generated").exists()
        assert (path / "wiki/hubs").exists()
        assert (path / "data/memory.db").exists()


def test_init_vault_raises_on_existing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        (path / "_index.md").write_text("")
        with pytest.raises(FileExistsError):
            init_vault(path)
