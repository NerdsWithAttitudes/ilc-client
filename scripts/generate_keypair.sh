#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-.secrets}"
ACTOR_ID="${2:-${TC_ACTOR_ID:-ilc-client-user}}"
mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SECRET_B64="${OUT_DIR}/ilc_falcon512_secret_key.b64"
PUBLIC_B64="${OUT_DIR}/ilc_public_key.b64"

DEFAULTS="$(PYTHONPATH="$ROOT/src" python3 - <<'PY' 2>/dev/null || true
from ilc.config import DEFAULT_SERVER_LIBRARY_ROOT, DEFAULT_CLIENT_LIBRARY_ROOT, SERVICE_ADMIN_EMAIL
print(DEFAULT_SERVER_LIBRARY_ROOT)
print(DEFAULT_CLIENT_LIBRARY_ROOT)
print(SERVICE_ADMIN_EMAIL)
PY
)"
SERVER_LIB="$(printf '%s\n' "$DEFAULTS" | sed -n '1p')"
CLIENT_LIB="$(printf '%s\n' "$DEFAULTS" | sed -n '2p')"
ADMIN_EMAIL="$(printf '%s\n' "$DEFAULTS" | sed -n '3p')"
SERVER_LIB="${SERVER_LIB:-/lib/applied-physics/ilc_server/0.1.0}"
CLIENT_LIB="${CLIENT_LIB:-/lib/applied-physics/ilc_client/0.1.0}"
ADMIN_EMAIL="${ADMIN_EMAIL:-ilc-admin@appliedphysics.org}"
ENV_TC_PUBLIC_KEY_B64="TC_PUBLIC_KEY_B64"
ENV_TC_BEARER_TOKEN="TC_BEARER_TOKEN"
ENV_TC_INSTALL_BEARER_TOKEN="TC_INSTALL_BEARER_TOKEN"
ENV_TC_ACTOR_ID="TC_ACTOR_ID"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import rjwt
getattr(rjwt.Actor, "new_falcon512")
PY
then
  echo "error: TinyChain rjwt-py with Falcon-512 support is required" >&2
  echo "install it with:" >&2
  echo '  pip install "rjwt-py @ git+https://github.com/TinyChain-Inc/rjwt.git#subdirectory=rjwt-py"' >&2
  exit 1
fi

"$PYTHON_BIN" - "${ACTOR_ID}" "${SECRET_B64}" "${PUBLIC_B64}" <<'PY'
import base64
import pathlib
import sys

import rjwt

actor_id = sys.argv[1]
if "/" in actor_id:
    raise SystemExit("Falcon-512 RJWT actor_id must not contain '/'; use a stable id such as ilc-ci-bot")
secret_path = pathlib.Path(sys.argv[2])
public_path = pathlib.Path(sys.argv[3])

actor = rjwt.Actor.new_falcon512(actor_id)
secret = base64.b64encode(actor.private_key_bytes()).decode("ascii")
public = base64.b64encode(actor.public_key_bytes()).decode("ascii")

secret_path.write_text(secret + "\n", encoding="utf-8")
public_path.write_text(public + "\n", encoding="utf-8")

public_bytes = base64.b64decode(public, validate=True)
if len(public_bytes) == 32:
    raise SystemExit("generated Ed25519-sized public key; expected Falcon-512")
PY

chmod 600 "${SECRET_B64}"

cat <<EOF
Generated Falcon-512 keypair:
  actor id:                 ${ACTOR_ID}
  secret key (keep secret): ${SECRET_B64}
  public key (share this):  ${PUBLIC_B64}

Required configuration:
  1) Send the public key value (from ${PUBLIC_B64}) to ${ADMIN_EMAIL}.
  2) Request Falcon-512 RJWT bearer tokens for:
     - runtime access to ${SERVER_LIB}
     - local WASM install access to ${CLIENT_LIB}
  3) Set runtime environment variables:
     export ${ENV_TC_ACTOR_ID}="${ACTOR_ID}"
     export ${ENV_TC_PUBLIC_KEY_B64}="\$(cat ${PUBLIC_B64})"
     export ${ENV_TC_BEARER_TOKEN}="<runtime token from admin>"
     export ${ENV_TC_INSTALL_BEARER_TOKEN}="<install token from admin>"
EOF
