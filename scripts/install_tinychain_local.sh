#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-.venv}"
if [[ "$VENV_DIR" = /* ]]; then
  VENV_PATH="$VENV_DIR"
else
  VENV_PATH="$ROOT/$VENV_DIR"
fi
PYTHON_BIN="${VENV_PATH}/bin/python"
PIP_BIN="${VENV_PATH}/bin/pip"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "error: Python virtualenv not found at $VENV_DIR; run ./scripts/bootstrap_and_test.sh first" >&2
  exit 1
fi

if "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import tinychain as tc
try:
    _ = tc.KernelHandle.local
except Exception:
    raise SystemExit(1)
PY
then
  echo "tinychain-local already available"
  exit 0
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "error: cargo is required to build tinychain-local" >&2
  echo "hint: install Rust toolchain and re-run" >&2
  exit 1
fi

"$PIP_BIN" install maturin

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

git clone --depth 1 https://github.com/TinyChain-Inc/client.git "$TMP_DIR/client"
git clone --depth 1 https://github.com/TinyChain-Inc/tc-server.git "$TMP_DIR/tc-server"
git clone --depth 1 https://github.com/TinyChain-Inc/tc-ir.git "$TMP_DIR/tc-ir"
git clone --depth 1 https://github.com/TinyChain-Inc/tc-state.git "$TMP_DIR/tc-state"
git clone --depth 1 https://github.com/TinyChain-Inc/tc-value.git "$TMP_DIR/tc-value"
mkdir -p "$TMP_DIR/deps"
git clone --depth 1 https://github.com/TinyChain-Inc/pathlink.git "$TMP_DIR/deps/pathlink"
git clone --depth 1 https://github.com/TinyChain-Inc/rjwt.git "$TMP_DIR/deps/rjwt"

(
  cd "$TMP_DIR/client/rust"
  VIRTUAL_ENV="$VENV_PATH" PATH="$VENV_PATH/bin:$PATH" "$VENV_PATH/bin/maturin" develop --release
)

"$PYTHON_BIN" - <<'PY'
import tinychain as tc
_ = tc.KernelHandle.local
print("tinychain-local installed")
PY
