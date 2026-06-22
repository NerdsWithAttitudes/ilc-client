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
- provider-neutral executable-encryption benchmark contracts and CLI
- one reference demonstration script: `a + b - c`

This repository does not contain proprietary implementation internals.

`ILCClient` is ciphertext-domain only. Its evaluator methods operate on
ciphertext payloads and do not expose separate exact-vs-approx client classes.

## Package map

- Server route wrapper: `ILCServer` in `src/ilc/library.py`
- Client route wrapper: `ILCClient` in `src/ilc/library.py`
- Runtime helpers: `build_local_kernel` and `wasm_install` in `src/ilc/runtime.py`
- Executable benchmark contracts/runtime: `src/ilc/executable/`
- Transport/auth execution: TinyChain built-ins (`tc.execute`, `tc.backend`,
  bearer-token flow in TinyChain client runtime)
- Demonstration script: [`examples/abc.py`](examples/abc.py)

## API surface

- Ciphertext evaluator ops: `add`, `mul`, `gemm`
- Route methods return `OpRef`; execute with `tc.execute(op)` inside
  `with tc.backend(...):`.
- The `a + b - c` script is a demonstration wrapper over these ciphertext ops.
- Executable benchmark CLI: `python -m ilc.executable.benchmark`.

### Reviewer-Facing Capability Split

The public API keeps one server wrapper and one client wrapper:

- `ILCServer`: `setup`, `encrypt`, `decrypt`
- `ILCClient`: `add`, `mul`, `gemm`

`ILCServer.setup` returns a public representative context. `encrypt` and
`decrypt` take that `public_context` explicitly; callers do not provide a
secret metric. `ILCClient` evaluator ops consume ciphertext-domain payloads
and the same public context for representative operations.

### Operation Dependency Matrix

- `setup`: server-side; derives metric/chart state from public parameters and
  server-held secret state.
- `encrypt`: server-side; requires `public_context`, shaped plaintext payload,
  and optional budget.
- `decrypt`: server-side; requires `public_context`, ciphertext, and opaque
  ciphertext handle.
- `add`: local evaluator-side; requires `public_context` and representative
  ciphertexts.
- `mul`: local evaluator-side; requires `public_context`, representative
  ciphertexts, and a planned witness for currently deployed ILC routes.
- `gemm`: local evaluator-side; requires `public_context`, representative
  ciphertexts, and a planned witness for currently deployed ILC routes.

Canonical public route methods use the `/chart/...` route family:

- server: `/chart/setup`, `/chart/encrypt`, `/chart/decrypt`, `/chart/record_eval`
- client: `/chart/add`, `/chart/exact/mul`, `/chart/exact/gemm`,
  `/chart/approx/mul`, `/chart/approx/gemm`

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
    nonce_dims=2,
)
# In a real run, execute setup_op with tinychain:
# setup_response = tc.execute(setup_op)
# public_context = setup_response["body"]["RepresentativeSetup"]["public_context"]
# (framework already decodes the response body into Python values)
setup_response = {
    "body": {"RepresentativeSetup": {"public_context": {"context_id": [0] * 16}}},
}
public_context = setup_response["body"]["RepresentativeSetup"]["public_context"]

# In a real run, open a backend context first. Route methods execute directly
# in eager mode and return Python-decoded responses.
with backend_context(kernel, bearer_token=token):
    setup_response = server.setup(
        params={"moduli": [65521, 65537, 65543], "params_id": [9] * 16},
        payload_dims=2,
        nonce_dims=2,
    )
    public_context = setup_response["body"]["RepresentativeSetup"]["public_context"]
    ciphertext = server.encrypt(
        public_context=public_context,
        payload=[7, 5],
        shape=[2],
        budget_log2=20,
    )
    sum_result = client.add(
        public_context=public_context,
        lhs_ciphertext=ciphertext["body"]["RepresentativeEncrypt"]["ciphertext"],
        rhs_ciphertext=ciphertext["body"]["RepresentativeEncrypt"]["ciphertext"],
    )

# Outside a backend context, the same calls return deferred route references.
sum_op = client.add(
    public_context=public_context,
    lhs_ciphertext={"limbs": [[1, 2]], "shape": [2]},
    rhs_ciphertext={"limbs": [[3, 4]], "shape": [2]},
)
```

## Default configuration constants

- server authority: `https://api.tctest.net`
- server library root: `/lib/applied-physics/ilc_server/0.1.0`
- client library root: `/lib/applied-physics/ilc_client/0.1.0`
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
# 1) Install dependencies and run the local contract suite
./scripts/bootstrap_and_test.sh

# 2) Generate a local keypair (public key only is shared)
./scripts/generate_keypair.sh

# 3) Request token from service administrator:
#    email the service administrator with:
#    - actor id (e.g. your-group/your-user)
#    - contents of .secrets/ilc_public_key.b64
#    - requested libs:
#      /lib/applied-physics/ilc_server/0.1.0
#      /lib/applied-physics/ilc_client/0.1.0

# 4) Set runtime credentials after receiving token
export TC_PUBLIC_KEY_B64="$(cat .secrets/ilc_public_key.b64)"
export TC_BEARER_TOKEN="<token from admin>"
export TC_INSTALL_BEARER_TOKEN="<client-library install token from admin>"
export TC_ACTOR_ID="your-group/your-user"
export TC_TOKEN_HOST="/lib/applied-physics/ilc_server/0.1.0"
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

## Executable encryption benchmark

The executable benchmark compares provider-neutral encrypted execution across
deterministic workloads. It times:

```text
input encryption + program encryption
-> node-by-node encrypted execution
-> output decryption
-> tolerance validation against plaintext reference
```

V1 carries a provider-owned encrypted-program artifact and times its creation.
For CKKS, `encrypt_program` deterministically encodes the executable graph as
opcode, adjacency, operand-selector, input-selector, and output-selector
tensors, then encrypts those tensors in the same CKKS session as the input
data. CKKS execution remains fully client-local and uses a provider-owned
`execute_program` path. The CKKS executor uses only the encrypted graph tensors,
encrypted inputs, and public shape/input/output metadata; it does not inspect
the plaintext graph's opcodes or edges during execution. The current
correctness-first scalar CKKS path is intentionally small and expensive because
encrypted selector application consumes multiplicative depth.

Known executable-program metadata leakage in V1 is explicit: node count,
topological position, per-node tensor shape, input IDs, output IDs, and tensor
dimensions are public so the executor can allocate and combine ciphertext
tensors. Opcodes and graph edges are represented by encrypted tensors. The
encrypted adjacency matrix is load-bearing in CKKS execution: operand selector
weights are gated by the encrypted adjacency entries for the candidate edges.

The client standardizes this representation as `EncryptedGraphProgram[T]`.
CKKS uses `EncryptedGraphProgram[CKKSEncryptedTensor]`; the planned ILC upgrade
will use `EncryptedGraphProgram[ILCEncryptedTensor]` with the same client-side
`ProgramEncoding`, metadata validation, and runtime dispatch contract.

Reviewer model:

```text
PlainProgram
-> ProgramEncoding tensors
   - opcode
   - adjacency
   - lhs_selector / rhs_selector
   - input_selector / output_selector
-> EncryptedGraphProgram[T]
-> provider.execute_program(encrypted_program, encrypted_inputs)
-> encrypted outputs
-> decrypt and validate
```

The executor may use public tensor shapes, input IDs, and output IDs to allocate
and route tensors. It must not inspect plaintext opcodes or plaintext graph
edges. Encrypted selectors choose candidate dataflow terms homomorphically.

| Provider | Program tensors encrypted? | Executor sees plaintext graph? | Status |
| --- | --- | --- | --- |
| `ckks` | Yes | No | Implemented scalar-packed baseline |
| `ilc` | Yes | No | Graph encryption implemented; execution fail-closed pending local selector scaling |
| `plaintext` | No | Yes | Reference baseline only |

For ILC, the server boundary remains setup plus shaped `/chart/encrypt` and
`/chart/decrypt`. Program encoding and executable-graph evaluation are client
responsibilities.

TFHE is intentionally not included in this PR. Its bit-level ciphertext model
is a poor fit for this quantitative tensor benchmark, where CKKS-style
approximate arithmetic evaluates real-valued matrix/tensor workloads directly.
A second approximate or arithmetic FHE backend would be the right next
portability check.

Plaintext smoke benchmark:

```bash
python -m ilc.executable.benchmark \
  --workload add_chain \
  --provider plaintext \
  --repeat 3 \
  --output-format json
```

Optional CKKS support requires OpenFHE Python:

```bash
pip install -e ".[ckks]"
python -m ilc.executable.benchmark \
  --workload mnist_linear_v1_b1 \
  --provider ckks \
  --repeat 1 \
  --output-format json
```

`--repeat 1` is a smoke-test setting. Use a larger repeat count for reported
benchmark numbers so setup/runtime noise is averaged. The default CKKS config
uses scalar packing, `multiplicative_depth=5`, and `scaling_technique="openfhe-auto"`.
That records the OpenFHE Python 1.5.x CKKS-RNS behavior validated here: leveled
execution with OpenFHE-managed rescale/level alignment. To test deeper
encrypted-selector circuits, construct `CKKSProvider(CKKSConfig(...))` with a
larger depth budget in Python rather than relying on the CLI defaults.

CKKS encrypted-graph benchmark snapshot from local validation on 2026-06-22:

- Python: 3.12.3
- OpenFHE Python: installed locally; package did not expose `__version__`
- Provider: `ckks`
- Benchmark repeat count: 1
- Output validation: all listed workloads passed
- Scope: correctness-first scalar-packed CKKS, not optimized SIMD CKKS
- Representation: `ckks_encrypted_graph_tensor_encoding_v1`

| Workload | Encrypt s | Execute s | Decrypt s | Total s | Max abs error |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mnist_linear_v1_b1` | 20.1085 | 47.6719 | 0.1028 | 67.8832 | 3.09e-13 |

This snapshot is not comparable to older public-schedule CKKS numbers because
the executor homomorphically applies encrypted graph selectors and encrypted
adjacency gates.

Generated JSON benchmark output is written to `benchmark-results/` when
`--output-path` is used. That directory is intentionally ignored by Git; copy
or archive reviewed result files separately when preparing paper artifacts.

The ILC provider uses only public `ILCServer`, `ILCClient`, TinyChain
execution, and WASM-install surfaces. Live ILC execution requires server
credentials and local WASM runtime prerequisites. In CI, the live executable
benchmark smoke runs only when the live-smoke gate is enabled.

The ILC tensor provider is a live integration adapter over the canonical
deployed ILC route contract. ILC executable-program encryption now constructs
the same `EncryptedGraphProgram[ILCEncryptedTensor]` artifact as CKKS, using
the existing shaped `/chart/encrypt` route for graph tensors. ILC encrypted
execution is fail-closed until `ILCClient` supports the local witness-free
encrypted selector-scaling primitive required by the shared encrypted-selector
interpreter; this avoids falling back to plaintext-graph execution for an
executable-encryption claim. The planned ILC execution path remains entirely
client-side: execute the shared encrypted graph over encrypted program tensors
and encrypted data using `ILCClient` homomorphic operations, then decrypt final
outputs with the existing shaped `/chart/decrypt` route. It requires no
additional Rust backend or server API changes. The benchmark snapshot above
records CKKS numbers only. Add separate ILC benchmark results when a specific
deployed ILC implementation is being evaluated.

## Maintenance

Development workflow and validation commands are in `DEVELOPMENT.md`.
CI configuration (including optional live integration checks against a deployed server) is also
documented there.
Contribution guidelines are in `CONTRIBUTING.md`.
Planned future work is tracked in `ROADMAP.md`.
