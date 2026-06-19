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

Follow-up work:

1. Packed/SIMD CKKS execution
- Replace the current correctness-first scalar packing with packed CKKS layouts
  for larger vector and matrix workloads.
- Record benchmark results with explicit machine and OpenFHE configuration
  metadata.

2. Larger executable benchmark fixtures
- Add reviewer-scale MNIST or similar inference fixtures that remain
  deterministic and package-resident.
- Keep fixture generation reproducible from checked-in scripts and avoid
  network downloads during benchmark execution.

3. Optional provider capabilities
- Add future operations through optional capability protocols or explicit
  capability discovery, not by growing the required provider protocol without a
  separate design note.

## Planned security upgrades

1. Post-quantum upgrade path for token signing/verification
- Track and adopt post-quantum security support in `rjwt`.
- Reference issue: https://github.com/TinyChain-Inc/rjwt/issues/4
- Goal: maintain compatibility guidance while migrating toward PQ-ready auth.

## Planned performance work

1. Memory and accelerator improvements in `ha-ndarray`
- Optimize memory usage to improve runtime efficiency for ILC workloads.
- Add explicit automatic GPU support where available.
- Goal: reduce memory pressure and improve throughput for evaluator operations.
