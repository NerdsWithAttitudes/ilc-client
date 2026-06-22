#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULTS="$(PYTHONPATH="$ROOT/src" "$PYTHON_BIN" - <<'PY' || true
from ilc.config import DEFAULT_LOCAL_AUTHORITY, DEFAULT_CLIENT_WASM_PATH
print(DEFAULT_LOCAL_AUTHORITY)
print(DEFAULT_CLIENT_WASM_PATH)
PY
)"
DEFAULT_SERVER="$(printf '%s\n' "$DEFAULTS" | sed -n '1p')"
DEFAULT_WASM_PATH="$(printf '%s\n' "$DEFAULTS" | sed -n '2p')"
DEFAULT_SERVER="${DEFAULT_SERVER:-http://127.0.0.1:8700}"
DEFAULT_WASM_PATH="${DEFAULT_WASM_PATH:-artifacts/cipher_wasm.wasm}"
SERVER="${ILC_INTEGRATION_SERVER:-$DEFAULT_SERVER}"
WASM_PATH="${ILC_WASM_PATH:-$ROOT/${DEFAULT_WASM_PATH}}"
ENV_TC_BEARER_TOKEN="TC_BEARER_TOKEN"
ENV_TC_INSTALL_BEARER_TOKEN="TC_INSTALL_BEARER_TOKEN"
ENV_TC_PUBLIC_KEY_B64="TC_PUBLIC_KEY_B64"
ENV_TC_ACTOR_ID="TC_ACTOR_ID"

missing=()
for var in "$ENV_TC_BEARER_TOKEN" "$ENV_TC_INSTALL_BEARER_TOKEN" "$ENV_TC_PUBLIC_KEY_B64" "$ENV_TC_ACTOR_ID"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "error: missing required env vars: ${missing[*]}" >&2
  echo "set them, then rerun. example:" >&2
  echo "  export ${ENV_TC_BEARER_TOKEN}=..." >&2
  echo "  export ${ENV_TC_INSTALL_BEARER_TOKEN}=..." >&2
  echo "  export ${ENV_TC_PUBLIC_KEY_B64}=..." >&2
  echo "  export ${ENV_TC_ACTOR_ID}=ilc-ci-bot" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/pip" install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
  "$VENV_DIR/bin/pip" install "rjwt-py @ git+https://github.com/TinyChain-Inc/rjwt.git#subdirectory=rjwt-py"
  "$VENV_DIR/bin/pip" install -e .
fi

./scripts/install_tinychain_local.sh

if [[ ! -f "$WASM_PATH" ]]; then
  echo "error: WASM path not found: $WASM_PATH" >&2
  echo "hint: set ILC_WASM_PATH or place artifact at artifacts/cipher_wasm.wasm" >&2
  exit 1
fi

"$VENV_DIR/bin/python" examples/abc.py \
  --server "$SERVER" \
  --wasm-path "$WASM_PATH" \
  --a "${ILC_A:-7}" \
  --b "${ILC_B:-5}" \
  --c "${ILC_C:-3}"
