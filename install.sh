#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.local/share/contextledger/venv"
LAUNCHER="$HOME/.local/bin/memory"

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

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "ERROR: python3-venv is not installed."
  echo
  echo "On Ubuntu/Debian, run:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python3-venv"
  echo
  echo "Then rerun:"
  echo "  ./install.sh"
  exit 1
fi

echo "Creating virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "Installing ContextLedger ..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -e . --quiet

mkdir -p "$HOME/.local/bin"
cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
exec "$HOME/.local/share/contextledger/venv/bin/memory" "$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

if ! echo "$PATH" | tr ':' '\n' | grep -q "^$HOME/.local/bin$"; then
  echo
  echo "WARNING: ~/.local/bin is not on your PATH."
  echo "Add this to your shell profile:"
  echo
  echo '  export PATH="$HOME/.local/bin:$PATH"'
  echo
fi

echo
echo "ContextLedger installed."
echo
echo "Run: memory --help"
