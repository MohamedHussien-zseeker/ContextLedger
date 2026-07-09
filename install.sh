#!/usr/bin/env bash
set -euo pipefail
python3 -m pip install --upgrade pip
python3 -m pip install -e .
echo "AI Memory OS installed. Run 'memory init' to get started."
