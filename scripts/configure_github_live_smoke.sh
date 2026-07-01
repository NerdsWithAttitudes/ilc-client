#!/usr/bin/env bash
set -euo pipefail
set +x

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

REPO="${GITHUB_REPO:-NerdsWithAttitudes/ilc-client}"
SECRETS_DIR="${SECRETS_DIR:-${ROOT}/.secrets}"
ACTOR_ID="${TC_ACTOR_ID:-ilc-ci-bot}"
TOKEN_HOST="${TC_TOKEN_HOST:-/lib/applied-physics/ilc_server/0.1.0}"
TOKEN_TTL_SECS="${TC_TOKEN_TTL_SECS:-3600}"

SECRET_KEY_FILE="${SECRETS_DIR}/ilc_falcon512_secret_key.b64"
PUBLIC_KEY_FILE="${SECRETS_DIR}/ilc_public_key.b64"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI 'gh' is required" >&2
  exit 1
fi

if [[ "$ACTOR_ID" == *"/"* ]]; then
  echo "error: TC_ACTOR_ID must not contain '/'; use a stable actor id such as ilc-ci-bot" >&2
  exit 1
fi

if [[ ! -f "$SECRET_KEY_FILE" || ! -f "$PUBLIC_KEY_FILE" ]]; then
  echo "error: missing Falcon key files under ${SECRETS_DIR}" >&2
  echo "generate them with: ./scripts/generate_keypair.sh" >&2
  exit 1
fi

SECRET_KEY_B64="$(tr -d '[:space:]' < "$SECRET_KEY_FILE")"
PUBLIC_KEY_B64="$(tr -d '[:space:]' < "$PUBLIC_KEY_FILE")"

python3 - "$SECRET_KEY_B64" "$PUBLIC_KEY_B64" <<'PY'
import base64
import sys

secret = base64.b64decode(sys.argv[1], validate=True)
public = base64.b64decode(sys.argv[2], validate=True)

if len(public) == 32:
    raise SystemExit("error: public key looks like Ed25519; expected Falcon-512")
if len(public) < 512:
    raise SystemExit(f"error: public key is unexpectedly short ({len(public)} bytes)")
if len(secret) <= len(public):
    raise SystemExit("error: secret key is unexpectedly short for Falcon-512")
PY

echo "Updating GitHub live-smoke token-minting configuration for ${REPO}..."
gh variable set TC_ACTOR_ID --repo "$REPO" --body "$ACTOR_ID"
gh variable set TC_TOKEN_HOST --repo "$REPO" --body "$TOKEN_HOST"
gh variable set TC_TOKEN_TTL_SECS --repo "$REPO" --body "$TOKEN_TTL_SECS"

gh secret set TC_FALCON512_SECRET_KEY_B64 --repo "$REPO" --body "$SECRET_KEY_B64"
gh secret set TC_PUBLIC_KEY_B64 --repo "$REPO" --body "$PUBLIC_KEY_B64"

cat <<EOF
GitHub token-minting configuration updated.

CI now mints fresh TC_BEARER_TOKEN and TC_INSTALL_BEARER_TOKEN values inside
each job from TC_FALCON512_SECRET_KEY_B64. The old expiring secrets
TC_BEARER_TOKEN and TC_INSTALL_BEARER_TOKEN are no longer read by the workflows.

Optional cleanup:
  gh secret delete TC_BEARER_TOKEN --repo ${REPO}
  gh secret delete TC_INSTALL_BEARER_TOKEN --repo ${REPO}
EOF
