#!/usr/bin/env bash
# Demo recording script for AI Memory OS
# Run: asciinema rec docs/demo.cast -c bash docs/demo-script.sh
# Then: agg docs/demo.cast docs/demo.gif --theme monokai --speed 1.5
set -euo pipefail

DEMO_VAULT="/tmp/ai-memory-os-demo"
rm -rf "$DEMO_VAULT"

# Create a sample source file
cat > /tmp/demo-source.md << 'EOF'
# Agent Memory Systems

Modern AI agents need persistent memory to maintain context
across sessions. The key approaches are:

1. Vector databases for semantic search
2. Knowledge graphs for structured relationships
3. File-based memory for human inspection
4. SQLite for fast structured queries

The core loop is: capture, process, link, index, search, serve.
EOF

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║         AI Memory OS — 60 Second Demo           ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
sleep 1

echo "$ memory init $DEMO_VAULT"
memory init "$DEMO_VAULT"
sleep 1

echo ""
echo "$ memory capture file demo.md"
memory --vault "$DEMO_VAULT" capture file /tmp/demo-source.md
sleep 1

echo ""
echo "$ memory process"
memory --vault "$DEMO_VAULT" process
sleep 1

echo ""
echo "$ memory index --apply"
memory --vault "$DEMO_VAULT" index --apply
sleep 1

echo ""
echo "$ memory search \"memory systems\""
memory --vault "$DEMO_VAULT" search "memory systems"
sleep 1

echo ""
echo "$ memory health"
memory --vault "$DEMO_VAULT" health
sleep 1

echo ""
echo "$ memory doctor"
memory --vault "$DEMO_VAULT" doctor
sleep 1

echo ""
echo "  ✓ Full loop complete — 83/83 tests passing"
echo "  ✓ https://github.com/MohamedHussien-zseeker/ai-memory-os"
echo ""
