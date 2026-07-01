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
  1) Send the public key value (from ${PUBLIC_B64}) to ${ADMIN_EMAIL}
     so the service verifier trusts this actor.
  2) For GitHub CI, run:
     ./scripts/configure_github_live_smoke.sh
     CI will mint short-lived Falcon-512 bearer tokens at job runtime.
  3) For local runs, mint short-lived tokens with:
     TC_FALCON512_SECRET_KEY_B64="\$(cat ${SECRET_B64})" \\
     TC_ACTOR_ID="${ACTOR_ID}" \\
     TC_TOKEN_HOST="${SERVER_LIB}" \\
     python scripts/mint_ci_tokens.py --print-env
  4) Set runtime environment variables:
     export ${ENV_TC_ACTOR_ID}="${ACTOR_ID}"
     export ${ENV_TC_PUBLIC_KEY_B64}="\$(cat ${PUBLIC_B64})"
     export TC_TOKEN_HOST="${SERVER_LIB}"
     # plus the TC_BEARER_TOKEN and TC_INSTALL_BEARER_TOKEN exports printed above
EOF
