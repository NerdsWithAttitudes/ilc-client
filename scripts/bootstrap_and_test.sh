#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

# Install TinyChain client directly from GitHub.
"$VENV_DIR/bin/pip" install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"

# Install this package in editable mode.
"$VENV_DIR/bin/pip" install -e .

# Test runner used by this repo.
"$VENV_DIR/bin/pip" install pytest

# Contract tests that do not require the public server to be live.
"$VENV_DIR/bin/python" -m pytest -q

cat <<MSG

Bootstrap + contract tests complete.
If api.tctest.net is not ready yet, run against a local/private server:
  $VENV_DIR/bin/python examples/abc.py --server http://127.0.0.1:8700

MSG
