#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TAPE="$SCRIPT_DIR/demo.tape"

# Create demo source file if missing
if [[ ! -f /tmp/demo-source.md ]]; then
  cat > /tmp/demo-source.md << 'SOURCE'
# Agent Memory Systems

Modern AI agents need persistent memory to maintain context
across sessions. The key approaches are:

1. Vector databases for semantic search
2. Knowledge graphs for structured relationships
3. File-based memory for human inspection
4. SQLite for fast structured queries

The core loop is: capture, process, link, index, search, serve.
SOURCE
fi

export VHS_NO_SANDBOX=1

echo "Building demo GIF..."
vhs "$TAPE" -o "$SCRIPT_DIR/demo.gif"

echo "Building demo MP4..."
vhs "$TAPE" -o "$SCRIPT_DIR/demo.mp4"

# Optional export
if [[ "${1:-}" == "--export" ]]; then
  EXPORT_DIR="/home/zghost-ubuntu/Downloads/for-github"
  if [[ -d "$EXPORT_DIR" ]]; then
    mkdir -p "$EXPORT_DIR"
    cp "$SCRIPT_DIR/demo.gif" "$SCRIPT_DIR/demo.mp4" "$EXPORT_DIR/"
    echo "Exported to $EXPORT_DIR/"
  else
    echo "Export dir not found: $EXPORT_DIR — skipping"
  fi
fi

echo "Done. Output files:"
ls -lh "$SCRIPT_DIR/demo.gif" "$SCRIPT_DIR/demo.mp4"
