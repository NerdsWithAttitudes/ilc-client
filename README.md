# ilc

Python integration package for Infinite Lattice Cryptography (ILC).

## Service and data-use disclaimer

- The public ILC Server currently has no service-level agreement (SLA).
- The ILC Server and this `ilc` client package are under active development.
  Interfaces and behavior may change, regress, or break without prior notice.
- Do not upload sensitive data to the ILC Server, including personally
  identifiable information (PII), protected health information (PHI), financial
  account data, regulated data, or confidential production data.

## Scope

This repository provides Python integration wrappers only:
- remote server calls for authenticated `encrypt` and `decrypt`
- local WASM calls for evaluator-side `add`, `mul`, and `gemm`
- one reference demonstration script: `a + b - c`

This repository does not contain proprietary implementation internals.

`ILCClient` is ciphertext-domain only. Its evaluator methods operate on
ciphertext payloads and do not expose separate exact-vs-approx client classes.

## Package map

- Server route wrapper: `ILCServer` in `src/ilc/library.py`
- Client route wrapper: `ILCClient` in `src/ilc/library.py`
- Runtime helpers: `build_local_kernel` and `wasm_install` in `src/ilc/runtime.py`
- Transport/auth execution: TinyChain built-ins (`tc.execute`, `tc.backend`,
  bearer-token flow in TinyChain client runtime)
- Demonstration script: [`examples/abc.py`](examples/abc.py)

## API surface

- Ciphertext evaluator ops: `add`, `mul`, `gemm`
- Route methods return `OpRef`; execute with `tc.execute(op)` inside
  `with tc.backend(...):`.
- The `a + b - c` script is a demonstration wrapper over these ciphertext ops.

### Reviewer-Facing Capability Split

The public API keeps one server wrapper and one client wrapper:

- `ILCServer`: `setup`, `encrypt`, `decrypt`
- `ILCClient`: `add`, `mul`, `gemm`

`ILCServer.encrypt/decrypt` require structured `CipherContext`. `ILCClient`
evaluator ops do not accept or require `CipherContext`.

### Operation Dependency Matrix

- `setup`: requires `secret_metric`
- `encrypt`: requires `CipherContext` (derived from setup with `secret_metric`)
- `decrypt`: requires `CipherContext` (derived from setup with `secret_metric`)
- `add`: does not require `CipherContext` or `secret_metric`
- `mul`: does not require `CipherContext` or `secret_metric`
- `gemm`: does not require `CipherContext` or `secret_metric`

### Reviewer Walkthrough

```python
import tinychain as tc
from ilc import ILCServer, ILCClient

server = ILCServer()
client = ILCClient()

# 1) Setup (secret-side)
setup_op = server.setup(
    params={"moduli": [65521, 65537, 65543], "params_id": [9] * 16},
    secret_metric=[3, 5, 7, 11],
    payload_dims=2,
    nonce_dims=2,
    nonce_bound=16,
)
# In a real run, execute setup_op with tinychain:
# setup_response = tc.execute(setup_op)
# context = setup_response["context"]
# public = setup_response["public"]
# (framework already decodes the response body into Python values)
setup_response = {
    "public": {"cipher_metric": [0, 0, 0, 0]},
    "context": {
        "version": 1,
        "alg": "HS256",
        "kid": "review",
        "payload_b64": "...",
        "signature_b64": "...",
    },
}
context = setup_response["context"]
public = setup_response["public"]

# 2) Secret-only operations (explicit context dependency)
ct_op = server.encrypt(
    context=context,
    payload=[7, 5],
    budget_log2=20,
)
pt_op = server.decrypt(
    context=context,
    ciphertext={"limbs": [[0, 1]], "key_id": [0] * 16, "params_id": [9] * 16, "budget_log2": 20, "max_budget_log2": 20},
)

# 3) Public evaluator operations (no CipherContext argument)
sum_op = client.add(metric=[3, 5], lhs=[1.0, 0.0], rhs=[2.0, 0.0])
prod_op = client.mul(metric=[3, 5], lhs=[1.0, 0.0], rhs=[2.0, 0.0])
gemm_op = client.gemm(
    metric=[3, 5],
    lhs=[1.0, 2.0, 3.0, 4.0],
    rhs=[5.0, 6.0, 7.0, 8.0],
    lhs_rows=2,
    lhs_cols=2,
    rhs_cols=2,
)

# Execute with TinyChain when running in backend scope.
sum_result = tc.execute(sum_op)
```

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

## Installation

```bash
pip install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
pip install -e .
```

## Reproducible run (`a + b - c`)

```bash
# 1) Install dependencies (editable)
pip install "tinychain @ git+https://github.com/TinyChain-Inc/client.git#subdirectory=py"
pip install -e .

# 2) Generate a local keypair (public key only is shared)
./scripts/generate_keypair.sh

# 3) Request token from service administrator:
#    email the service administrator with:
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
# optional but recommended: enforce WASM integrity at runtime
export ILC_CLIENT_WASM_SHA256="<sha256 hex of cipher_wasm.wasm>"

# 5) Verify configuration
python examples/abc.py --dry-run

# 6) Run the demonstration (requires prebuilt client WASM)
python examples/abc.py \
  --server https://api.tctest.net \
  --wasm-path /path/to/cipher_wasm.wasm \
  --a 7 --b 5 --c 3

```

Use `--json` for machine-readable output in automation.

If `ILC_CLIENT_WASM_SHA256` is set, runtime installation enforces that hash
before loading the WASM artifact.

## TinyChain execution model

- Normal mode: wrap execution with `with tc.backend(kernel, bearer_token=...):`
  and call route methods directly.
- Deferred mode: use `with tc.backend(..., auto_execute=False)` (or
  `mode="deferred"` where available), then call `tc.execute(opref)` explicitly.
- No package-local HTTP transport wrappers or custom response-envelope parsers
  are used.
- Client operation payloads in this package include only domain inputs.
- Active framework-gap candidates (if any) are tracked in `FRAMEWORK_GAPS.md`.

## Maintenance

Development workflow and validation commands are in `DEVELOPMENT.md`.
CI configuration (including optional live integration checks against a deployed server) is also
documented there.
Contribution guidelines are in `CONTRIBUTING.md`.
Planned future work is tracked in `ROADMAP.md`.
