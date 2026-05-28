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
- remote server calls for authenticated chart `setup`, `encrypt`, `decrypt`,
  `record_eval`, and exact/approximate planning
- local WASM calls for evaluator-side chart `add`, `exact_mul`, `exact_gemm`,
  `approx_mul`, and `approx_gemm`
- one reference route walkthrough: `examples/chart_v2.py`

This repository does not contain proprietary implementation internals.

`ILCClient` is ciphertext-domain only. Its evaluator methods operate on
ciphertext payloads and do not expose separate exact-vs-approx client classes.

## Package map

- Server route wrapper: `ILCServer` in `src/ilc/library.py`
- Client route wrapper: `ILCClient` in `src/ilc/library.py`
- Runtime helpers: `build_local_kernel` and `wasm_install` in `src/ilc/runtime.py`
- Transport/auth execution: TinyChain built-ins (`tc.execute`, `tc.backend`,
  bearer-token flow in TinyChain client runtime)
- Chart route walkthrough: [`examples/chart_v2.py`](examples/chart_v2.py)

## API surface

- Server ops: `setup`, `encrypt`, `decrypt`, `record_eval`,
  `exact_plan_mul`, `exact_plan_gemm`, `approx_plan_mul`, `approx_plan_gemm`
- Client evaluator ops: `add`, `exact_mul`, `exact_gemm`, `approx_mul`,
  `approx_gemm`
- Route methods return `OpRef`; execute with `tc.execute(op)` inside
  `with tc.backend(...):`.

### Reviewer-Facing Capability Split

The public API keeps one server wrapper and one client wrapper:

- `ILCServer`: `setup`, `encrypt`, `decrypt`, `record_eval`,
  `exact_plan_mul`, `exact_plan_gemm`, `approx_plan_mul`, `approx_plan_gemm`
- `ILCClient`: `add`, `exact_mul`, `exact_gemm`, `approx_mul`,
  `approx_gemm`

Addition is local through `ILCClient.add`. Multiplication and GEMM use a
server-planned witness and local evaluator execution: the server authorizes and
mints a fresh representative witness from opaque handles, and the local client
combines ciphertext bodies with that witness without decrypting plaintext or
using a refresh route.

### Operation Dependency Matrix

- `setup`: requires public parameters, payload dimension, representative
  dimension, and metric policy; it does not accept a user-provided secret metric
- `encrypt`: requires public chart context and plaintext payload
- `decrypt`: requires public chart context, representative ciphertext, and
  opaque handle
- `add`: requires public chart context and two representative ciphertext bodies;
  it does not receive handles or mask state
- `exact_plan_mul` / `exact_plan_gemm`: require public chart context plus
  opaque handles, and mint evaluator witnesses on the server
- `approx_plan_mul` / `approx_plan_gemm`: require public chart context,
  approximate opaque handles, error-ledger inputs, and validity budget; they
  mint evaluator witnesses on the server
- `exact_mul` / `exact_gemm` / `approx_mul` / `approx_gemm`: require public
  chart context, ciphertext tensors, and the server-planned witness; they
  execute locally in the evaluator WASM

### Reviewer Walkthrough

```python
import tinychain as tc
from ilc import ILCServer, ILCClient

server = ILCServer()
client = ILCClient()

# 1) Setup (secret-side)
setup_op = server.setup(
    params={"moduli": [65521, 65537, 65543], "params_id": [9] * 16},
    payload_dims=2,
    representative_dims=4,
    metric_policy="public-default",
)
# setup_response = tc.execute(setup_op)
# public_context = setup_response["public_context"]
public_context = {"context_id": [0] * 16}

# 2) Server encryption/decryption
ct_op = server.encrypt(
    public_context=public_context,
    payload=[7, 5],
)
pt_op = server.decrypt(
    public_context=public_context,
    ciphertext={"context_id": [0] * 16, "limbs": [[0, 1]]},
    handle={"context_id": [0] * 16, "handle": [0] * 32},
)

# 3) Local evaluator addition
sum_op = client.add(
    public_context=public_context,
    lhs_ciphertext={"context_id": [0] * 16, "limbs": [[0, 1]]},
    rhs_ciphertext={"context_id": [0] * 16, "limbs": [[2, 3]]},
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
# optional but recommended: enforce WASM integrity at runtime
export ILC_CLIENT_WASM_SHA256="<sha256 hex of cipher_wasm.wasm>"

# 5) Verify configuration
python examples/chart_v2.py --json

# 6) Run the demonstration (requires prebuilt client WASM)
python examples/chart_v2.py \
  --execute \
  --server https://api.tctest.net \
  --wasm-path /path/to/cipher_wasm.wasm \
  --json

```

Use `--json` for machine-readable output in automation.

## v2 chart route dry run

```bash
python examples/chart_v2.py --json
```

This prints the route sequence for chart setup/encrypt, local chart addition,
server-side additive handle recording, server-side planning, and local
evaluator multiplication/GEMM. It is a route contract walkthrough, not a local
cryptographic implementation.

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
