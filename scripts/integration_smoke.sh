#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-.venv}"
SERVER="${ILC_INTEGRATION_SERVER:-}"

if [[ -z "$SERVER" ]]; then
  echo "error: set ILC_INTEGRATION_SERVER to a local/private server URL" >&2
  exit 1
fi

"$VENV_DIR/bin/python" examples/chart_v2.py --execute --server "$SERVER"
