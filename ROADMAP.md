# Roadmap

This document tracks planned, public-facing directions for the `ilc` client
package and related ecosystem dependencies.

## Planned examples

1. Encrypted neural-network inference example (MNIST)
- Add a reference example demonstrating encrypted inference on the MNIST dataset.
- Target: reviewer-friendly, reproducible workflow using the public Python
  client surface (`ILCClient`, `ILCServer`) and the documented setup path.

## Planned security upgrades

1. Post-quantum upgrade path for token signing/verification
- Track and adopt post-quantum security support in `rjwt`.
- Reference issue: https://github.com/TinyChain-Inc/rjwt/issues/4
- Goal: keep the chart-route auth story stable while migrating toward PQ-ready auth.

## Planned performance work

1. Memory and accelerator improvements in `ha-ndarray`
- Optimize memory usage to improve runtime efficiency for ILC workloads.
- Add explicit automatic GPU support where available.
- Goal: reduce memory pressure and improve throughput for evaluator operations.
