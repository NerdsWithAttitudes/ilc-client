# Development

Maintainer reference for the public `ilc` package.

## Local setup

```bash
./scripts/bootstrap_and_test.sh
```

This script creates `.venv`, installs TinyChain from Git, installs `ilc` in
editable mode, and runs the package test suite with `pytest`.

## Baseline checks

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python examples/abc.py --dry-run --json
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

Required repository configuration for `Live ABC Smoke`:

- Variables:
  - `ILC_INTEGRATION_SERVER` (for example `https://<cloud-run-url>`)
  - `TC_TOKEN_HOST` (for example `/lib/applied-physics/ilc_server/0.1.0`)
  - `TC_ACTOR_ID` (for example `applied-physics/ci-bot`)
  - `ILC_CLIENT_WASM_SHA256` (hex sha256 of `cipher_wasm.wasm`)
- Secrets:
  - `TC_BEARER_TOKEN`
  - `TC_INSTALL_BEARER_TOKEN` (token authorized to install `/lib/applied-physics/ilc_client/0.1.0`)
  - `TC_PUBLIC_KEY_B64`
  - one of:
    - `ILC_CLIENT_WASM_B64` (base64-encoded wasm), or
    - `ILC_CLIENT_WASM_URL` (download URL for wasm)

Local equivalent before push:

```bash
export ILC_CLIENT_WASM_SHA256="$(sha256sum /absolute/path/to/cipher_wasm.wasm | awk '{print $1}')"
```

Runtime requirements for local WASM check:
- Rust toolchain (`cargo`) available
- `maturin` (installed automatically by `scripts/install_tinychain_local.sh`)
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

## Scope reminder

- Keep this repo limited to public Python wrapper code and examples.
- Do not commit WASM artifacts.
- Do not add proprietary Rust source, private credentials, or internal runbooks.
