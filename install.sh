#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.local/share/contextledger/venv"
LAUNCHER="$HOME/.local/bin/memory"

# Detect Termux
IS_TERMUX=false
if [ -n "${PREFIX:-}" ] && [ -d "${PREFIX:-}/bin" ]; then
  IS_TERMUX=true
fi
if [ -f "/system/build.prop" ] && grep -q "ro.build.version.sdk" /system/build.prop 2>/dev/null; then
  IS_TERMUX=true
fi

# Termux prerequisites
if $IS_TERMUX; then
  if ! command -v rustc >/dev/null 2>&1 || ! command -v clang >/dev/null 2>&1; then
    echo "ERROR: Missing build tools on Termux."
    echo
    echo "Install required packages:"
    echo "  pkg update"
    echo "  pkg install python rust clang make pkg-config openssl libffi"
    echo
    echo "Then rerun:"
    echo "  ./install.sh"
    exit 1
  fi

  # Set ANDROID_API_LEVEL if not set
  if [ -z "${ANDROID_API_LEVEL:-}" ]; then
    if command -v getprop >/dev/null 2>&1; then
      export ANDROID_API_LEVEL
      ANDROID_API_LEVEL=$(getprop ro.build.version.sdk)
      echo "Detected ANDROID_API_LEVEL=$ANDROID_API_LEVEL"
    else
      echo "WARNING: Cannot detect ANDROID_API_LEVEL."
      echo "Set it manually: export ANDROID_API_LEVEL=33"
    fi
  fi
fi

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

# Use writable temp directory (Termux may have read-only /tmp)
TEMP_BASE="${TMPDIR:-${PREFIX:-/tmp}/tmp}"
if ! mkdir -p "$TEMP_BASE" 2>/dev/null; then
  TEMP_BASE="$HOME/tmp"
  mkdir -p "$TEMP_BASE"
fi
TMP_VENV=$(mktemp -d -p "$TEMP_BASE")

if ! python3 -m venv "$TMP_VENV" >/dev/null 2>&1; then
  rm -rf "$TMP_VENV"
  if $IS_TERMUX; then
    echo "ERROR: Failed to create virtual environment."
    echo
    echo "Ensure python is installed:"
    echo "  pkg install python"
    echo
    echo "Then rerun:"
    echo "  ./install.sh"
  else
    echo "ERROR: python3-venv is not installed or incomplete."
    echo
    echo "On Ubuntu/Debian, run:"
    echo "  sudo apt update"
    echo "  sudo apt install -y python3-venv"
    echo
    echo "Then rerun:"
    echo "  ./install.sh"
  fi
  exit 1
fi
rm -rf "$TMP_VENV"

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

# Install cl-context bridge script
CL_CONTEXT="$HOME/.local/bin/cl-context"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/bin/cl-context" ]; then
  cp "$SCRIPT_DIR/bin/cl-context" "$CL_CONTEXT"
  chmod +x "$CL_CONTEXT"
fi

# Add to PATH for current session
export PATH="$HOME/.local/bin:$PATH"

if ! echo "$PATH" | tr ':' '\n' | grep -q "^$HOME/.local/bin$"; then
  echo
  echo "WARNING: ~/.local/bin is not on your PATH."
  echo
  if $IS_TERMUX; then
    echo "Add this to your shell profile:"
    echo
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    echo
    echo "Or run:"
    echo '  echo "export PATH=\"$HOME/.local/bin:$PATH\"" >> ~/.bashrc'
    echo '  source ~/.bashrc'
  else
    echo "Add this to your shell profile:"
    echo
    echo '  export PATH="$HOME/.local/bin:$PATH"'
  fi
fi

echo
echo "ContextLedger installed."
echo
echo "Run: memory --help"