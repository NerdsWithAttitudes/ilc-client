# Contributing

Thank you for contributing to `ilc`.

This repository is the public Python integration surface for Infinite Lattice
Cryptography (ILC). It is intended for reproducible integration, examples, and
review-oriented usability improvements.

## Scope of accepted contributions

Accepted:
- Python wrapper ergonomics for `ILCClient` and `ILCServer`
- Example scripts and documentation improvements
- Tests and CI improvements for public integration workflows
- Non-proprietary helper tooling around package installation and usage

Not accepted in this repository:
- Proprietary Rust implementation internals
- Private credentials, tokens, allowlists, or deployment secrets
- Committed WASM artifacts (`*.wasm`)
- Private operational runbooks

## Service and data-use disclaimer

- The ILC Server has no service-level agreement (SLA) at this time.
- The ILC Server and this client package are under active development and may
  change or break without notice.
- Do not submit, upload, or test with sensitive data, including personally
  identifiable information (PII), protected health information (PHI), financial
  account data, regulated data, or confidential production data.

## Security and boundary requirements

- Keep this repository dependency-light and public-safe.
- Do not add source code copied from private repositories.
- Never commit secret material:
  - `.secrets/`
  - auth tokens
  - private keys
- Keep WASM artifacts out of git; use external artifact URLs or local files.

## Development setup

Use the maintainer workflow in [`DEVELOPMENT.md`](DEVELOPMENT.md):

```bash
./scripts/bootstrap_and_test.sh
```

## Pull request expectations

Please include:
- a clear summary of user-visible changes
- tests for behavioral changes
- documentation updates for API or workflow changes

Before opening a PR:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python examples/chart_v2.py --json
```

If your change touches live integration workflows, also run:

```bash
./scripts/ci_preflight.sh
```

## Code style

- Favor explicit, typed Python interfaces.
- Keep route contract semantics stable unless a change is intentional and
  documented.
- Prefer concise, technical prose in comments and docs.
- Avoid introducing package-local transport/auth abstractions when TinyChain
  already provides canonical surfaces.

## Licensing

By contributing, you agree your contribution is provided under this repository's
license terms (see [`LICENSE`](LICENSE)).

## Contributor legal representation and assignment

By submitting any contribution (including code, documentation, tests, examples,
or other materials) to this repository, you represent and warrant that:

- you are the sole author of the contribution, or you otherwise have full legal
  right and authority to submit it;
- the contribution does not knowingly infringe any copyright, trade secret,
  patent, trademark, or other proprietary right of any third party;
- the contribution is not subject to any license, contractual restriction, or
  other encumbrance that would prevent its use, modification, distribution, or
  relicensing by project maintainers.

By submitting the contribution, you irrevocably assign all right, title, and
interest in and to the contribution, including all associated intellectual
property rights, to The ILC Authors, to the maximum extent permitted by
applicable law.

If assignment is not permitted in your jurisdiction, you grant The ILC Authors
a perpetual, irrevocable, worldwide, transferable, sublicensable, royalty-free
license to use, reproduce, modify, distribute, publicly perform, and publicly
display the contribution in any medium.
