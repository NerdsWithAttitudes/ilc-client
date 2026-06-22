#!/usr/bin/env bash
set -euo pipefail

ENABLE="${ILC_ENABLE_LIVE_SMOKE:-0}"
if [[ "$ENABLE" != "1" ]]; then
  echo "live integration check disabled (ILC_ENABLE_LIVE_SMOKE=$ENABLE); skipping config enforcement"
  exit 0
fi

missing=()
for key in ILC_INTEGRATION_SERVER ILC_CLIENT_WASM_SHA256 TC_BEARER_TOKEN TC_INSTALL_BEARER_TOKEN TC_PUBLIC_KEY_B64 TC_TOKEN_HOST TC_ACTOR_ID; do
  if [[ -z "${!key:-}" ]]; then
    missing+=("$key")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "error: missing required CI config: ${missing[*]}" >&2
  exit 1
fi

for token_var in TC_BEARER_TOKEN TC_INSTALL_BEARER_TOKEN; do
  token_value="${!token_var}"
  if [[ "$token_value" =~ ^[[:space:]]*[Bb]earer[[:space:]]+ ]]; then
    echo "error: ${token_var} must be the raw RJWT token, not an Authorization header" >&2
    exit 1
  fi
  if [[ "$token_value" == "<"*">" || "$token_value" == *"from admin"* ]]; then
    echo "error: ${token_var} still looks like a placeholder" >&2
    exit 1
  fi
done

if [[ "$TC_ACTOR_ID" == *"/"* ]]; then
  echo "error: TC_ACTOR_ID must not contain '/'; use a stable actor id such as ilc-ci-bot" >&2
  exit 1
fi

python3 - <<'PY'
import base64
import json
import os
import sys
import time

public_key = os.environ["TC_PUBLIC_KEY_B64"].strip()
try:
    public_bytes = base64.b64decode(public_key, validate=True)
except Exception as exc:
    raise SystemExit(f"error: TC_PUBLIC_KEY_B64 is not valid base64: {exc}") from exc

if len(public_bytes) == 32:
    raise SystemExit("error: TC_PUBLIC_KEY_B64 looks like an Ed25519 public key; expected Falcon-512")
if len(public_bytes) < 512:
    raise SystemExit(
        f"error: TC_PUBLIC_KEY_B64 is unexpectedly short ({len(public_bytes)} bytes); expected Falcon-512"
    )

def decode_jwt_payload(token: str, label: str) -> dict:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise SystemExit(f"error: {label} is not a 3-part RJWT/JWT token")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"error: could not decode {label} claims: {exc}") from exc

def collect_lib_claims(payload: dict, seen: set[str] | None = None) -> set[str]:
    seen = seen or set()
    custom = payload.get("custom")
    if isinstance(custom, list) and custom and isinstance(custom[0], str):
        seen.add(custom[0])
    inherit = payload.get("inherit")
    if isinstance(inherit, str) and inherit:
        collect_lib_claims(decode_jwt_payload(inherit, "inherited token"), seen)
    return seen

def validate_token_claims(env_name: str, *, required_libs: tuple[str, ...]) -> None:
    label = env_name
    payload = decode_jwt_payload(os.environ[env_name], label)
    expected_actor = os.environ["TC_ACTOR_ID"]
    expected_host = os.environ["TC_TOKEN_HOST"].rstrip("/")
    actor = payload.get("actor_id")
    issuer = str(payload.get("iss", "")).rstrip("/")
    if actor != expected_actor:
        raise SystemExit(
            f"error: {label} actor_id mismatch: expected {expected_actor!r}, got {actor!r}"
        )
    if issuer != expected_host:
        raise SystemExit(
            f"error: {label} issuer mismatch: expected TC_TOKEN_HOST={expected_host!r}, got {issuer!r}"
        )
    now = time.time()
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise SystemExit(f"error: {label} is missing numeric exp claim")
    if exp <= now:
        raise SystemExit(f"error: {label} is expired; mint a fresh Falcon-512 token")
    iat = payload.get("iat")
    if isinstance(iat, (int, float)) and iat > now + 600:
        raise SystemExit(
            f"error: {label} iat is more than 10 minutes in the future; check token clock/source"
        )
    claims = collect_lib_claims(payload)
    missing = [lib for lib in required_libs if lib.rstrip("/") not in {claim.rstrip("/") for claim in claims}]
    if missing:
        formatted_claims = ", ".join(sorted(claims)) or "<none>"
        raise SystemExit(
            f"error: {label} missing required library claim(s): {', '.join(missing)}; "
            f"decoded claims: {formatted_claims}"
        )

token_host = os.environ["TC_TOKEN_HOST"].rstrip("/")
client_lib = "/lib/applied-physics/ilc_client/0.1.0"
validate_token_claims("TC_BEARER_TOKEN", required_libs=(token_host,))
validate_token_claims("TC_INSTALL_BEARER_TOKEN", required_libs=(token_host, client_lib))
PY

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
