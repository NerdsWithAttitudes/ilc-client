#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-.secrets}"
mkdir -p "${OUT_DIR}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PRIVATE_PEM="${OUT_DIR}/ilc_ed25519_private.pem"
PUBLIC_B64="${OUT_DIR}/ilc_public_key.b64"

DEFAULTS="$(PYTHONPATH="$ROOT/src" python3 - <<'PY' || true
from ilc.config import DEFAULT_SERVER_LIBRARY_ROOT, DEFAULT_CLIENT_LIBRARY_ROOT, SERVICE_ADMIN_EMAIL
print(DEFAULT_SERVER_LIBRARY_ROOT)
print(DEFAULT_CLIENT_LIBRARY_ROOT)
print(SERVICE_ADMIN_EMAIL)
PY
)"
SERVER_LIB="$(printf '%s\n' "$DEFAULTS" | sed -n '1p')"
CLIENT_LIB="$(printf '%s\n' "$DEFAULTS" | sed -n '2p')"
ADMIN_EMAIL="$(printf '%s\n' "$DEFAULTS" | sed -n '3p')"
SERVER_LIB="${SERVER_LIB:-/lib/applied-physics/ilc/0.1.0}"
CLIENT_LIB="${CLIENT_LIB:-/lib/applied-physics/ilc-client/0.1.0}"
ADMIN_EMAIL="${ADMIN_EMAIL:-$(printf '%s@%s' haydn appliedphysics.org)}"
ENV_TC_PUBLIC_KEY_B64="TC_PUBLIC_KEY_B64"
ENV_TC_BEARER_TOKEN="TC_BEARER_TOKEN"
ENV_TC_INSTALL_BEARER_TOKEN="TC_INSTALL_BEARER_TOKEN"

if ! command -v openssl >/dev/null 2>&1; then
  echo "error: openssl is required" >&2
  exit 1
fi

openssl genpkey -algorithm Ed25519 -out "${PRIVATE_PEM}" >/dev/null 2>&1
openssl pkey -in "${PRIVATE_PEM}" -pubout -outform DER \
  | tail -c 32 \
  | base64 \
  | tr -d '\n' > "${PUBLIC_B64}"

python3 - "${PUBLIC_B64}" <<'PY'
import base64
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = path.read_text(encoding="utf-8").strip()
decoded = base64.b64decode(value, validate=True)
if len(decoded) != 32:
    raise SystemExit(f"invalid public key length: expected 32 bytes, got {len(decoded)}")
PY

chmod 600 "${PRIVATE_PEM}"

cat <<EOF
Generated keypair:
  private key (keep secret): ${PRIVATE_PEM}
  public key (share this):   ${PUBLIC_B64}

Required configuration:
  1) Send the public key value (from ${PUBLIC_B64}) to ${ADMIN_EMAIL}.
  2) Request an access token for:
     - ${SERVER_LIB}
     - ${CLIENT_LIB}
  3) Set runtime environment variables:
     export ${ENV_TC_PUBLIC_KEY_B64}="\$(cat ${PUBLIC_B64})"
     export ${ENV_TC_BEARER_TOKEN}="<token from admin>"
     export ${ENV_TC_INSTALL_BEARER_TOKEN}="\$${ENV_TC_BEARER_TOKEN}"
EOF
