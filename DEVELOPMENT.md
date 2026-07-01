# Development

Maintainer reference for the public `ilc` package.

## Local setup

```bash
./scripts/bootstrap_and_test.sh
```

This script creates `.venv`, installs TinyChain from Git, installs TinyChain's
`rjwt-py` Falcon-512 bindings, installs `ilc` in editable mode, and runs the
package test suite with `pytest`.

## Baseline checks

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python examples/abc.py --dry-run --json
./.venv/bin/python -m ilc.executable.benchmark --workload add_chain --provider plaintext --repeat 3 --output-format json
```

## Local integration check

Use this when a local or private ILC server is available:

```bash
ILC_INTEGRATION_SERVER=http://127.0.0.1:8700 ./scripts/integration_smoke.sh
```

## Parent-repo local live-smoke parity

When working from the private parent `ilc` repository, prefer the parent smoke
script for end-to-end local reproduction of the GitHub `Live ABC Smoke` job:

```bash
cd /path/to/ilc
bash ci/run_ilc_wasm_python_smoke.sh
```

That script supplies the inputs which are normally GitHub repository
variables/secrets:

- builds `target/wasm32-unknown-unknown/release/examples/cipher_wasm.wasm`;
- starts a local `ilc-http-server`;
- reads the test identity from `ilc-server/auth.example.toml`;
- mints a runtime bearer token and a separate client-library install token;
- exports `TC_BEARER_TOKEN`, `TC_INSTALL_BEARER_TOKEN`, `TC_TOKEN_HOST`,
  `TC_ACTOR_ID`, and `TC_PUBLIC_KEY_B64`;
- runs `ilc-client-public/examples/abc.py` against the local server.

Use this path to reproduce token, WASM-install, route, and local-kernel issues
before updating public GitHub secrets. Running `scripts/ci_live_smoke.sh` from
this public repo still requires those values to be provided explicitly.

## GitHub Actions live integration check

Workflow: `.github/workflows/ci.yml`

- `Contract Tests` always runs (`pytest` + `examples/abc.py --dry-run --json`).
- `Live ABC Smoke` runs only when repository variable `ILC_ENABLE_LIVE_SMOKE=1`.
- Scheduled config drift check: `.github/workflows/preflight.yml`.

`Live ABC Smoke` validates the public client against the deployed/live backend.
It is expected to fail until that backend has been updated to the route
contract expected by this client branch and trusts the configured Falcon-512
CI public key. Keep `ILC_ENABLE_LIVE_SMOKE=0` for this PR unless the live
backend has already been upgraded.

Required repository configuration for `Live ABC Smoke`:

- Variables:
  - `ILC_INTEGRATION_SERVER` (for example `https://<cloud-run-url>`)
  - `TC_TOKEN_HOST` (for example `/lib/applied-physics/ilc_server/0.1.0`)
  - `TC_ACTOR_ID` (for example `ilc-ci-bot`; Falcon-512 actor IDs must not contain `/`)
  - `TC_TOKEN_TTL_SECS` (optional; defaults to `3600`)
  - `ILC_CLIENT_WASM_SHA256` (hex sha256 of `cipher_wasm.wasm`)
- Secrets:
  - `TC_FALCON512_SECRET_KEY_B64`
  - `TC_PUBLIC_KEY_B64`
  - one of:
    - `ILC_CLIENT_WASM_B64` (base64-encoded wasm), or
    - `ILC_CLIENT_WASM_URL` (download URL for wasm)

Configure the token-minting secrets and variables from a local Falcon keypair:

```bash
./scripts/configure_github_live_smoke.sh
```

Do not store `TC_BEARER_TOKEN` or `TC_INSTALL_BEARER_TOKEN` as GitHub secrets.
The workflows mint those short-lived tokens inside each job from
`TC_FALCON512_SECRET_KEY_B64`, which avoids scheduled/live-smoke failures from
expired static bearer tokens.

Local equivalent before push:

```bash
export ILC_CLIENT_WASM_SHA256="$(sha256sum /absolute/path/to/cipher_wasm.wasm | awk '{print $1}')"
```

Runtime requirements for local WASM check:
- Rust toolchain (`cargo`) available
- `maturin` (installed automatically by `scripts/install_tinychain_local.sh`)
- TinyChain `rjwt-py` installed from
  `https://github.com/TinyChain-Inc/rjwt.git#subdirectory=rjwt-py`
- network access to clone TinyChain public repos:
  - `https://github.com/TinyChain-Inc/client.git`
  - `https://github.com/TinyChain-Inc/tc-server.git`
  - `https://github.com/TinyChain-Inc/tc-ir.git`
  - `https://github.com/TinyChain-Inc/tc-state.git`
  - `https://github.com/TinyChain-Inc/tc-value.git`

Release governance checklist:
- `RELEASE_CHECKLIST.md`

Framework-gap tracking:
- `FRAMEWORK_GAPS.md`

## Executable benchmark checks

Baseline executable benchmark checks require no OpenFHE, WASM, or live ILC
service:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ilc.executable.benchmark \
  --workload add_chain \
  --provider plaintext \
  --repeat 3 \
  --output-format json
```

CKKS checks require optional OpenFHE Python and are skipped or fail with a
public missing-dependency error when OpenFHE is unavailable:

```bash
./.venv/bin/python -m pytest -q -m "ckks"
./.venv/bin/python -m ilc.executable.benchmark \
  --workload mnist_linear_v1_b1 \
  --provider ckks \
  --repeat 1 \
  --output-format json
```

Use `repeat=1` only as a smoke check. For reportable benchmark numbers, run a
larger repeat count and archive the JSON/CSV output outside Git.

ILC executable benchmark checks require the same live credentials and local
WASM prerequisites as the ABC smoke:

```bash
./scripts/ci_preflight.sh
./scripts/executable_benchmark_smoke.sh
```

By default this runs `mnist_linear_v1_b1` with `provider=ckks`, because CKKS is
the implemented executable-encryption backend. Override with
`ILC_EXECUTABLE_WORKLOAD`, `ILC_EXECUTABLE_PROVIDER`, or
`ILC_EXECUTABLE_REPEAT`. The ILC executable provider remains fail-closed until
local encrypted selector scaling is implemented.

## Scope reminder

- Keep this repo limited to public Python wrapper code and examples.
- Do not commit WASM artifacts.
- Do not add proprietary Rust source, private credentials, or internal runbooks.
