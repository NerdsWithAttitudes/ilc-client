# ilc

Public Python integration package for Infinite Lattice Cryptography (ILC).

## Scope

This repository provides client-facing Python wrappers only:
- remote server calls for authenticated `encrypt` and `decrypt`
- local WASM calls for evaluator-side `add`, `mul`, and `gemm`
- one source-visible demonstration script: `a + b - c`

It does not contain proprietary Rust implementation internals.

## Reviewer map

- Server route wrapper: `ILCServer` in `src/ilc/library.py`
- Client route wrapper: `ILCClient` in `src/ilc/library.py`
- Auth/session wrapper: `AuthContext` and `ILCServerSession` in `src/ilc/library.py`
- Demonstration script: [examples/abc.py](examples/abc.py)

## Default configuration constants

- server authority: `https://api.tctest.net`
- server library root: `/lib/applied-physics/ilc/0.1.0`
- client library root: `/lib/applied-physics/ilc-client/0.1.0`
- default local authority: `http://127.0.0.1:8700`
- default WASM path: `artifacts/cipher_wasm.wasm` (not committed)
- local compute defaults: `ilc.DEFAULT_COMPUTE` (`metric`)

These are exposed from `ilc.config` and can be overridden.

## Terms

- `metric`: the encrypted-coordinate basis parameters used by ILC operations
- `payload`: plaintext vector before encryption (for scalar demos, value is in slot 0)
- `nonce`: extra random dimensions mixed into encryption for privacy hardening
- `payload_dims` / `nonce_dims`: how many payload and nonce slots are embedded in each ciphertext

The public client request contract does not include any `blind` parameter.

## Install (editable)

```bash
pip install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
pip install -e .
```

## Reproducible procedure

```bash
# 1) Install dependencies
pip install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
pip install -e .

# 2) Generate a local keypair (public key only is shared)
./scripts/generate_keypair.sh

# 3) Request token from admin:
#    email ilc-admin@appliedphysics.org with:
#    - actor id (e.g. your-group/your-user)
#    - contents of .secrets/ilc_public_key.b64
#    - requested libs:
#      /lib/applied-physics/ilc/0.1.0
#      /lib/applied-physics/ilc-client/0.1.0

# 4) Set runtime credentials after receiving token
export TC_PUBLIC_KEY_B64="$(cat .secrets/ilc_public_key.b64)"
export TC_BEARER_TOKEN="<token from admin>"
export TC_INSTALL_BEARER_TOKEN="$TC_BEARER_TOKEN"
export TC_ACTOR_ID="your-group/your-user"
export TC_TOKEN_HOST="/lib/applied-physics/ilc/0.1.0"

# 5) Verify configuration only
python examples/abc.py --dry-run

# 6) Run the demonstration (requires prebuilt client WASM)
python examples/abc.py \
  --server https://api.tctest.net \
  --wasm-path /path/to/cipher_wasm.wasm \
  --a 7 --b 5 --c 3

```

Use `--json` for machine-readable output.

## Local validation helpers

```bash
./scripts/bootstrap_and_test.sh
ILC_INTEGRATION_SERVER=http://127.0.0.1:8700 ./scripts/integration_smoke.sh
./scripts/run_abc_quickstart.sh
```
