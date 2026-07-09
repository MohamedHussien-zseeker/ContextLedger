import tempfile
from pathlib import Path

from memory.doctor import check
from memory.vault import init_vault


def test_doctor_healthy_vault():
    with tempfile.TemporaryDirectory() as tmp:
        vp = Path(tmp) / "test-vault"
        init_vault(vp)
        result = check(vp)
        assert result["healthy"] is True
        assert len(result["issues"]) == 0


def test_doctor_missing_vault():
    result = check(Path("/nonexistent/path"))
    assert result["healthy"] is False
    assert len(result["issues"]) >= 1
