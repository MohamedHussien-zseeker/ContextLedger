"""Tests for install.sh — verify preflight checks exist."""
import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parents[1] / "install.sh"


def test_install_script_is_bash():
    content = INSTALL_SH.read_text()
    assert content.startswith("#!/usr/bin/env bash")


def test_install_script_checks_python3():
    content = INSTALL_SH.read_text()
    assert "command -v python3" in content


def test_install_script_checks_version():
    content = INSTALL_SH.read_text()
    assert "sys.version_info >= (3, 11)" in content


def test_install_script_checks_pip():
    content = INSTALL_SH.read_text()
    assert "python3 -m pip --version" in content


def test_install_script_installs_editable():
    content = INSTALL_SH.read_text()
    assert "pip install -e ." in content


def test_install_script_has_set_e():
    content = INSTALL_SH.read_text()
    assert "set -euo pipefail" in content
