"""Tests for install.sh — verify preflight checks and venv install."""
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parents[1] / "install.sh"


def test_install_script_is_bash():
    content = INSTALL_SH.read_text()
    assert content.startswith("#!/usr/bin/env bash")


def test_install_script_has_set_e():
    content = INSTALL_SH.read_text()
    assert "set -euo pipefail" in content


def test_install_script_checks_python3():
    content = INSTALL_SH.read_text()
    assert "command -v python3" in content


def test_install_script_checks_version():
    content = INSTALL_SH.read_text()
    assert "sys.version_info >= (3, 11)" in content


def test_install_script_checks_venv():
    content = INSTALL_SH.read_text()
    assert "python3 -m venv" in content
    assert "mktemp" in content


def test_install_script_creates_venv_dir():
    content = INSTALL_SH.read_text()
    assert ".local/share/contextledger/venv" in content


def test_install_script_creates_launcher():
    content = INSTALL_SH.read_text()
    assert ".local/bin/memory" in content


def test_install_script_does_not_use_break_system_packages():
    content = INSTALL_SH.read_text()
    assert "--break-system-packages" not in content


def test_install_script_does_not_use_system_pip():
    content = INSTALL_SH.read_text()
    lines = content.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "pip install" in stripped:
            assert "python3 -m pip install" not in stripped


def test_install_script_warns_path():
    content = INSTALL_SH.read_text()
    assert "~/.local/bin" in content
    assert "PATH" in content
