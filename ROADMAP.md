# Roadmap

This document tracks planned, public-facing directions for the `ilc` client
package and related ecosystem dependencies.

## Planned examples

1. Encrypted neural-network inference example (MNIST)
- Add a reference example demonstrating encrypted inference on the MNIST dataset.
- Target: reviewer-friendly, reproducible workflow using the public Python
  client surface (`ILCClient`, `ILCServer`) and the documented setup path.

## Planned executable-encryption benchmark improvements

The provider-neutral executable benchmark is implemented in
`src/ilc/executable/`, with usage and validation documented in `README.md` and
`DEVELOPMENT.md`.

### Shaped encryption prerequisite and client-side executable encryption

Before claiming patent-shaped executable-program encryption, the canonical ILC
encrypt/decrypt contract should support **general shaped payloads**. Matrices,
tensors, and executable-program encodings are all ordinary shaped payloads.
Executable encryption itself remains a **client-side feature**.

Target model:

```text
shape + flattened integer/fixed-point payload + declared scale/budget
-> existing server /chart/encrypt
-> ciphertext body + opaque handle + tensor metadata
```

This should support matrices and tensors generally, including executable-program
encoding tensors such as adjacency matrices, opcode vectors, shape tables, and
input/output index maps. The server does not receive or understand an
executable-program object.

Canonical route policy:

- keep a single server encryption route;
- keep a single server decryption route;
- generalize the encrypt/decrypt payload contract to include shape metadata;
- do not add tensor-specific route names;
- do not add executable-program server endpoints or server-side executable
  program types.

Preferred canonical routes:

- server: `/chart/encrypt`
- server: `/chart/decrypt`

Expected request/response contracts:

- public chart context;
- payload `shape`;
- flattened `payload`;
- declared `scale_bits` and/or `budget_log2`;
- encrypted tensor wrapper containing ciphertext, handle, shape, packed length,
  scale, and representation metadata.

Implementation rules:

- Reuse the existing chart encrypt/decrypt route ownership and internals for
  the flattened payload.
- Treat missing shape as a flat payload with shape `[payload.len()]`.
- Validate `product(shape) == payload.len()`.
- Validate rank, dimensions, and payload capacity before encryption.
- Keep shape/scale metadata public and payload encryption generic.
- Do not add an executable-program-specific backend primitive, backend type, or
  route.
- Do not multiply endpoint concepts for scalar, vector, matrix, tensor, or
  executable-program payloads; these are all shaped payloads under the same
  encrypt/decrypt surface.
- Keep server ownership limited to setup, shaped-payload encryption, and
  shaped-payload decryption.
- Keep executable-program encoding and execution entirely out of the server.

Validation gates:

- tensor round-trip for vectors, matrices, and rank-3 tensors;
- shape mismatch rejects before encryption;
- decrypted payload preserves original shape and scale metadata;
- scalar/vector `/chart/encrypt` behavior remains valid under the generalized
  shaped-payload contract;
- executable benchmark can use shaped-payload encryption for non-data tensors
  without adding server knowledge of executable programs.

Patent-shaped executable-program encryption is layered as:

```text
PlainProgram
-> client-side graph/tensor encoding
-> ordinary shaped-payload encryption for adjacency/opcode/metadata tensors
-> encrypted program artifact
-> provider-owned encrypted-program execution path
```

The benchmark runtime validates public program metadata, then delegates to the
provider's typed `execute_program(encrypted_program, encrypted_inputs)` method.
It does not provide a plaintext graph-walk path for executable-encryption
claims. CKKS implements encrypted-selector execution now. ILC encrypts the same
program tensor artifact and fails closed until the local evaluator exposes the
selector-scaling primitive needed to run that artifact entirely client-side. The
server must not execute the encrypted program and must not receive the operation
DAG during evaluation.

Required end-state workflow:

```text
client encodes PlainProgram as graph/tensor payloads
-> server /chart/encrypt encrypts program payloads with the same context as the data
-> server /chart/encrypt encrypts input tensors
-> client/WASM executes encrypted program over encrypted inputs
-> server /chart/decrypt decrypts encrypted outputs
```

Server responsibilities:

- setup;
- shaped-payload encryption for data tensors and program-encoding tensors;
- shaped-payload decryption for outputs.

Server non-responsibilities:

- no executable-program route;
- no executable-program request/response type;
- no adjacency-matrix, opcode, or graph semantics;
- no operation DAG during evaluation;
- no client-side evaluation or online per-node executable-program assistance.

Client/WASM responsibilities:

- deterministic `PlainProgram` to graph/tensor encoding;
- encryption orchestration using ordinary server `/chart/encrypt`;
- local ciphertext-domain `add`, `mul`, and `gemm`;
- encrypted-program execution over encrypted inputs;
- output orchestration using ordinary server `/chart/decrypt`;
- no setup, encrypt, decrypt, auth, or secret-metric handling in the WASM
  evaluator artifact.

Client-side executable engineering procedure:

1. Program encoding
- `ProgramEncoding` is defined in the public client layer.
- Encode `PlainProgram` deterministically as shaped payload tensors:
  - opcode selector tensor;
  - adjacency matrix;
  - left-operand selector matrix;
  - right-operand selector matrix;
  - input selector matrix;
  - output selector matrix;
  - shape/lane metadata.
- Keep this encoding out of `ilc-types`, `ilc-server`, and `ilc-core`.

2. Program encryption
- `ILCProvider.encrypt_program` encodes `PlainProgram` locally.
- It calls ordinary server `/chart/encrypt` for each program tensor using the
  same `public_context` as input-data encryption.
- It returns an `EncryptedGraphProgram[ILCEncryptedTensor]` containing
  encrypted program tensors and public execution dimensions.
- This is the same provider-neutral artifact shape used by CKKS as
  `EncryptedGraphProgram[CKKSEncryptedTensor]`.

3. Client-side execution
- Require a provider-owned `execute_program` implementation for executable
  encryption.
- CKKS receives encrypted program tensors, encrypted input tensors, and public
  execution dimensions, then runs an oblivious encrypted-selector interpreter
  without inspecting plaintext opcodes or graph edges.
- ILC must use the same `EncryptedGraphProgram[ILCEncryptedTensor]` artifact
  once its local evaluator exposes the required selector-scaling primitive.
- This remains entirely client-side and must not require additional Rust backend
  or server API changes.

4. Runtime dispatch
- The public runtime requires a typed `execute_program` provider capability.
- Use it for ILC patented executable-encryption benchmarks.
- Fail closed when the ILC provider lacks client-side encrypted-program
  execution.
- CKKS now encrypts the graph tensors and uses client-local provider-owned
  encrypted-selector execution. Its encrypted adjacency tensor is load-bearing
  in candidate edge routing. Its scalar-packed V1 is a correctness and
  benchmarking baseline, not an optimized SIMD implementation.
- Plaintext remains the public-DAG reference baseline.

Client-side validation gates:

- deterministic program encoding for equivalent `PlainProgram` inputs;
- one-hot opcode and selector tensors before encryption;
- encrypted program tensors and encrypted data tensors use one context;
- no executable-program types or routes are added to `ilc-server`;
- no executable-program types are added to `ilc-types`;
- provider execution consumes encrypted-program tensors, not plaintext opcodes
  or plaintext graph edges;
- no server calls occur during encrypted-program execution;
- CKKS encrypted-program execution decrypts to the same outputs as plaintext DAG
  execution for encrypted-selector smoke workloads.
- ILC executable-program encryption produces
  `EncryptedGraphProgram[ILCEncryptedTensor]`.
- ILC encrypted-program execution fails closed until `ILCClient` exposes the
  witness-free encrypted selector-scaling primitive needed by the same
  client-side encrypted-selector interpreter used by CKKS.

Follow-up work:

1. ILC provider wiring for the shared encrypted-selector interpreter
- Reuse the client-side encrypted graph interpreter validated by CKKS.
- Implement the ILC provider adapter primitives needed by that interpreter:
  encrypted selector scaling, zero-like tensors, tensor summation, and shape
  admissible `add`, `mul`, and `gemm` over `ILCEncryptedTensor`.
- Preserve the existing encrypted graph artifact and program tensor encoding;
  only the ILC execution hooks are incomplete.
- Use only `ILCClient` homomorphic operations during execution.
- Use `ILCServer` only for existing shaped `/chart/encrypt` and
  `/chart/decrypt` calls at the encryption/decryption boundary.
- Do not add Rust backend routes, server API endpoints, server-side executable
  types, setup/decrypt logic in the evaluator, or server-visible DAG data.
- Fail closed until ILC decrypts the same encrypted-selector smoke workloads as
  CKKS.

2. Packed/SIMD CKKS execution
- Replace the current correctness-first scalar packing with packed CKKS layouts
  for larger vector and matrix workloads.
- Record benchmark results with explicit machine and OpenFHE configuration
  metadata.

3. Larger executable benchmark fixtures
- Add reviewer-scale MNIST or similar inference fixtures that remain
  deterministic and package-resident.
- Keep fixture generation reproducible from checked-in scripts and avoid
  network downloads during benchmark execution.

4. Optional provider capabilities
- Add future operations through optional capability protocols or explicit
  capability discovery, not by growing the required provider protocol without a
  separate design note.

## Planned security upgrades

1. Post-quantum upgrade path for token signing/verification
- Track and adopt post-quantum security support in `rjwt`.
- Reference issue: https://github.com/TinyChain-Inc/rjwt/issues/4
- Goal: maintain clear migration guidance while adopting PQ-ready auth.

## Planned performance work

1. Memory and accelerator improvements in `ha-ndarray`
- Optimize memory usage to improve runtime efficiency for ILC workloads.
- Add explicit automatic GPU support where available.
- Goal: reduce memory pressure and improve throughput for evaluator operations.
