#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_DIR="${VENV_DIR:-.venv}"
SERVER="${ILC_INTEGRATION_SERVER:-}"
TOKEN="${TC_BEARER_TOKEN:-}"
INSTALL_TOKEN="${TC_INSTALL_BEARER_TOKEN:-}"
PUBKEY="${TC_PUBLIC_KEY_B64:-}"
TOKEN_HOST="${TC_TOKEN_HOST:-/lib/applied-physics/ilc_server/0.1.0}"
WASM_SHA256="${ILC_CLIENT_WASM_SHA256:-}"

if [[ -z "$SERVER" ]]; then
  echo "error: ILC_INTEGRATION_SERVER is required" >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "error: TC_BEARER_TOKEN is required" >&2
  exit 1
fi

if [[ -z "$INSTALL_TOKEN" ]]; then
  echo "error: TC_INSTALL_BEARER_TOKEN is required" >&2
  echo "  It must authorize installing /lib/applied-physics/ilc_client/0.1.0 into the local TinyChain kernel." >&2
  echo "  Do not reuse TC_BEARER_TOKEN unless that token was minted with the client-library install claim." >&2
  exit 1
fi

if [[ -z "$PUBKEY" ]]; then
  echo "error: TC_PUBLIC_KEY_B64 is required" >&2
  exit 1
fi

if [[ -z "$WASM_SHA256" ]]; then
  echo "error: ILC_CLIENT_WASM_SHA256 is required" >&2
  exit 1
fi

mkdir -p artifacts
WASM_PATH="${ILC_WASM_PATH:-$ROOT/artifacts/cipher_wasm.wasm}"

if [[ ! -f "$WASM_PATH" ]]; then
  if [[ -n "${ILC_CLIENT_WASM_B64:-}" ]]; then
    printf '%s' "$ILC_CLIENT_WASM_B64" | base64 -d > "$WASM_PATH"
  elif [[ -n "${ILC_CLIENT_WASM_URL:-}" ]]; then
    curl -fsSL "$ILC_CLIENT_WASM_URL" -o "$WASM_PATH"
  else
    echo "error: provide ILC_WASM_PATH or one of ILC_CLIENT_WASM_B64 / ILC_CLIENT_WASM_URL" >&2
    exit 1
  fi
fi

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(sha256sum "$WASM_PATH" | awk '{print tolower($1)}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(shasum -a 256 "$WASM_PATH" | awk '{print tolower($1)}')"
else
  echo "error: need sha256sum or shasum to verify wasm integrity" >&2
  exit 1
fi

EXPECTED_SHA256="$(printf '%s' "$WASM_SHA256" | tr '[:upper:]' '[:lower:]')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  echo "error: wasm sha256 mismatch" >&2
  echo "  expected: $EXPECTED_SHA256" >&2
  echo "  actual:   $ACTUAL_SHA256" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/pip" install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
  "$VENV_DIR/bin/pip" install -e .
fi

./scripts/install_tinychain_local.sh

export TC_BEARER_TOKEN="$TOKEN"
export TC_INSTALL_BEARER_TOKEN="$INSTALL_TOKEN"
export TC_PUBLIC_KEY_B64="$PUBKEY"
export TC_TOKEN_HOST="$TOKEN_HOST"
export ILC_INTEGRATION_SERVER="$SERVER"
export ILC_WASM_PATH="$WASM_PATH"

"$VENV_DIR/bin/python" examples/abc.py \
  --server "$SERVER" \
  --wasm-path "$WASM_PATH" \
  --json
