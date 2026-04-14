#!/usr/bin/env bash
set -euo pipefail

ENABLE="${ILC_ENABLE_LIVE_SMOKE:-0}"
if [[ "$ENABLE" != "1" ]]; then
  echo "live integration check disabled (ILC_ENABLE_LIVE_SMOKE=$ENABLE); skipping config enforcement"
  exit 0
fi

missing=()
for key in ILC_INTEGRATION_SERVER ILC_CLIENT_WASM_SHA256 TC_BEARER_TOKEN TC_PUBLIC_KEY_B64 TC_TOKEN_HOST TC_ACTOR_ID; do
  if [[ -z "${!key:-}" ]]; then
    missing+=("$key")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "error: missing required CI config: ${missing[*]}" >&2
  exit 1
fi

if [[ -z "${TC_INSTALL_BEARER_TOKEN:-}" ]]; then
  echo "warning: TC_INSTALL_BEARER_TOKEN is empty, CI will reuse TC_BEARER_TOKEN"
fi

if [[ -n "${ILC_WASM_PATH:-}" ]]; then
  if [[ ! -f "${ILC_WASM_PATH}" ]]; then
    echo "error: ILC_WASM_PATH is set but file does not exist: ${ILC_WASM_PATH}" >&2
    exit 1
  fi
elif [[ -z "${ILC_CLIENT_WASM_B64:-}" && -z "${ILC_CLIENT_WASM_URL:-}" ]]; then
  echo "error: set ILC_WASM_PATH or one of ILC_CLIENT_WASM_B64 / ILC_CLIENT_WASM_URL" >&2
  exit 1
fi

echo "live integration preflight configuration is complete"
