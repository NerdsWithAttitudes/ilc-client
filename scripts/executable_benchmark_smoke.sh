#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-.venv}"
WORKLOAD="${ILC_EXECUTABLE_WORKLOAD:-mnist_linear_v1_b1}"
PROVIDER="${ILC_EXECUTABLE_PROVIDER:-ckks}"
REPEAT="${ILC_EXECUTABLE_REPEAT:-1}"

"$VENV_DIR/bin/python" -m ilc.executable.benchmark \
  --workload "$WORKLOAD" \
  --provider "$PROVIDER" \
  --repeat "$REPEAT" \
  --output-format json
