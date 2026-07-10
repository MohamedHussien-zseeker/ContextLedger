#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required but was not found."
  exit 1
fi

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
  echo "ERROR: Python 3.11+ is required."
  echo "Found: $(python3 --version)"
  exit 1
fi

if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "ERROR: python3-pip is not installed."
  echo
  echo "On Ubuntu/Debian, run:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python3-pip"
  echo
  echo "Then rerun:"
  echo "  ./install.sh"
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -e .

echo "ContextLedger installed. Run 'memory init' to get started."
