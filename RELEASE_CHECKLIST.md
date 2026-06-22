# Release Checklist

This checklist defines the standard process for publishing a testable ILC client
WASM artifact and validating it through `ilc-client-public` CI.

## 1) Build and publish WASM (private ILC repo)

1. Build `cipher_wasm.wasm` from the private ILC repository.
2. Compute digest:
   - `sha256sum cipher_wasm.wasm`
3. Publish the WASM to an immutable versioned URL:
   - GitHub release asset or versioned object storage URL.
4. Keep a matching release note entry with:
   - artifact URL
   - SHA-256
   - source commit/tag

Automation:
- Private repo workflow: `.github/workflows/publish-ilc-client-wasm.yml`
- Inputs:
  - `release_tag`
  - `public_repo` (default `NerdsWithAttitudes/ilc-client-public`)
  - `publish_release`
- Required secret in private repo when publishing:
  - `PUBLIC_REPO_PAT` (repo-write PAT for target public repo)

## 2) Provision CI test identity

1. Generate a dedicated CI keypair.
2. Add CI public key to ILC server allowlist.
3. Mint a test token for CI actor with least-privilege route scope and short TTL.
4. Confirm token audience/host aligns with:
   - `/lib/applied-physics/ilc_server/0.1.0`
   - `/lib/applied-physics/ilc_client/0.1.0`

## 3) Configure `ilc-client-public` GitHub repo

Repository variables:

- `ILC_ENABLE_LIVE_SMOKE=1`
- `ILC_INTEGRATION_SERVER=https://<cloud-run-url>`
- `TC_TOKEN_HOST=/lib/applied-physics/ilc_server/0.1.0`
- `ILC_CLIENT_WASM_SHA256=<sha256-hex>`

Repository secrets:

- `TC_BEARER_TOKEN=<ci token>`
- `TC_INSTALL_BEARER_TOKEN=<ci install token authorized for /lib/applied-physics/ilc_client/0.1.0>`
- `TC_PUBLIC_KEY_B64=<ci public key b64>`
- one of:
  - `ILC_CLIENT_WASM_URL=<immutable versioned URL>`
  - `ILC_CLIENT_WASM_B64=<base64 wasm>`

## 4) Local parity check before push

Run public package checks from `ilc-client-public`:

```bash
./scripts/bootstrap_and_test.sh
```

Run the full local equivalent of the GitHub `Live ABC Smoke` job from the
private parent `ilc` repo:

```bash
cd /path/to/ilc
bash ci/run_ilc_wasm_python_smoke.sh
```

The parent script builds the client WASM, starts a local `ilc-http-server`,
mints both required bearer tokens, and runs
`ilc-client-public/examples/abc.py` with the same local-kernel install path used
by CI.

## 5) CI pass criteria

- `Contract Tests` passes.
- `Live ABC Smoke` preflight step passes (no missing config).
- `Live ABC Smoke` run passes end-to-end against deployed server.

## 6) Drift guard

- Public repo workflow `.github/workflows/preflight.yml` runs scheduled preflight
  checks for required live-smoke variables/secrets.
