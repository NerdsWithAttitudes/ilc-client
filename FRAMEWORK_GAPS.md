# Framework Gaps

## Active candidates

1. Route return-state should preserve declared Python type
- classification: `framework-gap`
- status: open
- rationale: method signatures can declare concrete return types, but callers
  may still receive generic JSON-like values at runtime. The framework should
  decode to the declared type consistently.
- impact in this package: evaluator result parsing stays in package code
  (`src/ilc/example_ops.py`) instead of relying on framework-native typed decode.

2. Route method bodies should have typed field declarations
- classification: `framework-gap`
- status: open
- rationale: public wrapper methods currently serialize ILC-specific request
  bodies as plain Python dictionaries because TinyChain `opref.get/post` accept
  generic bodies at this layer. A framework-native typed field declaration would
  reduce duplicated string keys without adding package-local request schemas.
- impact in this package: `src/ilc/library.py` keeps small route-wrapper methods
  with string-key request bodies until the framework exposes a typed route body
  declaration surface.
