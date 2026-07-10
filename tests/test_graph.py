import tempfile
from pathlib import Path

from memory.graph import health
from memory.vault import init_vault


def test_health_empty_vault():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        result = health(vp)
        assert result["total_notes"] >= 1  # _index.md
        assert result["connected_pct"] >= 0


def test_health_with_linked_notes():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        (vp / "04-Knowledge/note-a.md").write_text("# Note A\n\nLink to [[note-b]].")
        (vp / "04-Knowledge/note-b.md").write_text("# Note B\n\nLink to [[note-a]].")
        result = health(vp)
        assert result["connected"] >= 2
        assert result["generated_isolated"] == 0
